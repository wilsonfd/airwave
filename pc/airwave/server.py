# -*- coding: utf-8 -*-
"""AirWave streaming server.

Design notes (these are the fixes for the stutter in the old version):

* 10 ms PCM packets by default instead of 5 ms.  Same latency class, half the
  wake-ups and far fewer chances for the Windows scheduler to bunch packets.
* Capture callback only copies bytes into a tiny queue.  A dedicated sender
  thread owns all socket I/O, so a slow NIC can never stall the audio callback.
* The queue is depth-limited: when Python gets descheduled we drop stale audio
  instead of building an ever-growing latency backlog.
* SIO_UDP_CONNRESET is disabled, so the ICMP "port unreachable" storm after a
  phone disconnects can never upset recvfrom().
* Clients are kept for 15 s without a HELLO (the old 3 s timeout could drop a
  phone whose background timer got coalesced by iOS, producing a periodic
  one-second audio hole).
* META is retransmitted every 1.25 s and on every HELLO, so a lost metadata
  datagram cannot leave the phone silent.
"""
from __future__ import annotations

import json
import math
import queue
import re
import socket
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Tuple

import pyaudiowpatch as pyaudio

from .protocol import (
    DEFAULT_PORT, build_audio, build_meta, parse_control,
)
from .winutil import time_period, udp_port_in_use

CLIENT_TIMEOUT = 15.0
META_INTERVAL = 1.25
MAX_QUEUE = 6
# One UDP datagram must stay below the WiFi/Ethernet MTU.  1400 bytes total
# leaves room for IPv4+UDP headers and avoids IP fragmentation, which is a
# major (and often invisible) cause of audio dropouts on WiFi.
MAX_DATAGRAM_BYTES = 1400
AUDIO_HEADER_BYTES = 5


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    clean_name: str
    kind: str                 # system | virtual | input
    rate: int
    channels: int
    is_default: bool = False

    @property
    def kind_label(self) -> str:
        return {"system": "系统声音", "virtual": "虚拟声卡", "input": "麦克风"}[self.kind]

    @property
    def display(self) -> str:
        return f"{self.clean_name}  ·  {self.kind_label}"

    @property
    def detail(self) -> str:
        return f"{self.rate} Hz · {'立体声' if self.channels >= 2 else '单声道'}"


@dataclass
class Client:
    addr: Tuple[str, int]
    first_seen: float
    last_seen: float
    hellos: int = 0
    packets: int = 0


@dataclass
class Snapshot:
    running: bool = False
    ready: bool = False
    rate: int = 0
    channels: int = 0
    packet_ms: float = 7.0
    port: int = DEFAULT_PORT
    clients: List[dict] = field(default_factory=list)
    level: float = 0.0
    levels: List[float] = field(default_factory=list)
    packets_sent: int = 0
    bytes_sent: int = 0
    dropped: int = 0
    send_errors: int = 0
    uptime: float = 0.0
    stream_id: str = ""
    device_name: str = ""
    ips: List[str] = field(default_factory=list)
    queue_depth: int = 0
    error: str = ""


def _is_cable(name: str) -> bool:
    n = name.lower()
    return ("cable" in n) or ("vb-audio" in n) or ("voicemeeter" in n)


def _clean_name(name: str) -> str:
    return name.replace(" [Loopback]", "").strip()


def _ip_rank(ip: str) -> int:
    if ip.startswith("192.168."):
        return 0
    if ip.startswith("10."):
        return 1
    if re.match(r"^172\.(1[6-9]|2\d|3[01])\.", ip):
        return 2
    return 3


def local_ips() -> List[str]:
    ips: List[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    ips = [ip for ip in ips if not ip.startswith("169.254.")]
    ips.sort(key=lambda x: (_ip_rank(x), x))
    return ips


def _rms_level(pcm: bytes, channels: int) -> float:
    """Perceptual 0..1 level, cheap enough to run at 100 Hz."""
    try:
        mv = memoryview(pcm).cast("h")
        n = len(mv)
        if n <= 0:
            return 0.0
        step = max(1, n // 480)
        total = 0
        count = 0
        for i in range(0, n, step):
            v = mv[i]
            total += v * v
            count += 1
        rms = math.sqrt(total / max(1, count))
        # Music usually sits around 3k-9k RMS; map that range nicely.
        return min(1.0, (rms / 11000.0) ** 0.62)
    except Exception:
        return 0.0


class AudioServer:
    """Capture + UDP fan-out.  Safe to drive from a GUI thread."""

    def __init__(self, log_cb: Optional[Callable[[str], None]] = None):
        self._log_cb = log_cb or (lambda _m: None)
        self._lock = threading.RLock()
        self._clients: Dict[Tuple[str, int], Client] = {}
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=MAX_QUEUE)
        self._levels: Deque[float] = deque(maxlen=120)
        self._running = threading.Event()
        self._ready = threading.Event()
        self._threads: List[threading.Thread] = []
        self._sock: Optional[socket.socket] = None
        self._stream = None
        self._port = DEFAULT_PORT
        self._rate = 0
        self._channels = 0
        self._packet_ms = 7.0
        self._frames = 0
        self._frame_size = 4
        self._device_name = ""
        self._stream_id = ""
        self._seq = 0
        self._packets_sent = 0
        self._bytes_sent = 0
        self._dropped = 0
        self._send_errors = 0
        self._callback_errors = 0
        self._level = 0.0
        self._uptime_start = 0.0
        self._open_error = ""
        self._server_name = (socket.gethostname() or "PC").split(".")[0]
        self._ips: List[str] = local_ips()

    # ------------------------------------------------------------------ log
    def _log(self, msg: str) -> None:
        try:
            self._log_cb(msg)
        except Exception:
            pass

    # -------------------------------------------------------------- devices
    @staticmethod
    def list_devices() -> List[DeviceInfo]:
        p = pyaudio.PyAudio()
        out: List[DeviceInfo] = []
        seen: set[int] = set()
        try:
            try:
                api = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                api_index = int(api["index"])
                default_idx = int(api["defaultOutputDevice"])
                try:
                    default_name = p.get_device_info_by_index(default_idx)["name"]
                except Exception:
                    default_name = ""
            except Exception:
                api_index = -1
                default_name = ""

            # WASAPI loopback endpoints: capture whatever the PC is playing.
            try:
                for d in p.get_loopback_device_info_generator():
                    idx = int(d["index"])
                    name = str(d["name"])
                    clean = _clean_name(name)
                    kind = "virtual" if _is_cable(name) else "system"
                    is_default = bool(default_name) and (
                        clean == default_name or default_name in clean or clean in default_name)
                    out.append(DeviceInfo(
                        index=idx, name=name, clean_name=clean, kind=kind,
                        rate=int(d.get("defaultSampleRate") or 48000),
                        channels=max(1, min(2, int(d.get("maxInputChannels") or 2))),
                        is_default=is_default))
                    seen.add(idx)
            except Exception as exc:
                self._log_safe(f"枚举系统声音失败: {exc}")

            # Real capture endpoints (VB-Cable's CABLE Output, microphones...).
            try:
                for i in range(p.get_device_count()):
                    d = p.get_device_info_by_index(i)
                    idx = int(d["index"])
                    if idx in seen or int(d.get("hostApi", -1)) != api_index:
                        continue
                    if int(d.get("maxInputChannels") or 0) <= 0:
                        continue
                    name = str(d["name"])
                    kind = "virtual" if _is_cable(name) else "input"
                    out.append(DeviceInfo(
                        index=idx, name=name, clean_name=_clean_name(name), kind=kind,
                        rate=int(d.get("defaultSampleRate") or 48000),
                        channels=max(1, min(2, int(d["maxInputChannels"]))),
                        is_default=False))
                    seen.add(idx)
            except Exception as exc:
                self._log_safe(f"枚举输入设备失败: {exc}")
        finally:
            p.terminate()

        # Default output first, then other system loopbacks, virtual cables, mics.
        def key(d: DeviceInfo):
            order = {"system": 0, "virtual": 1, "input": 2}[d.kind]
            return (0 if d.is_default else 1, order, d.clean_name.lower())

        out.sort(key=key)
        return out

    @staticmethod
    def _log_safe(msg: str) -> None:
        # Device enumeration has no instance logger; keep it silent but useful.
        pass

    # ----------------------------------------------------------------- start
    def start(self, device_index: int, device_name: str, port: int,
              rate: int = 48000, channels: int = 2, packet_ms: int = 7) -> None:
        if self._running.is_set():
            self.stop()
        port = int(port)
        if not (1024 <= port <= 65535):
            raise ValueError("端口需在 1024–65535 之间")
        if udp_port_in_use(port):
            raise RuntimeError(
                f"端口 {port} 已被占用（可能另一个 AirWave 或旧版推流端正在运行），请换一个端口")
        packet_ms = int(packet_ms)
        if not (2 <= packet_ms <= 50):
            packet_ms = 7

        self._open_error = ""
        self._ready.clear()
        self._device_name = device_name
        self._packet_ms = packet_ms
        self._port = port
        self._stream_id = uuid.uuid4().hex[:12]
        self._rate = 0
        self._channels = 0
        self._frames = 0
        self._seq = 0
        self._packets_sent = self._bytes_sent = self._dropped = 0
        self._send_errors = self._callback_errors = 0
        self._level = 0.0
        self._levels.clear()
        with self._lock:
            self._clients.clear()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # On Windows SO_REUSEADDR lets two processes bind the same UDP port and
        # silently steal each other's datagrams.  Refuse to start instead.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 512 * 1024)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 128 * 1024)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except OSError:
                pass
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as exc:
            sock.close()
            raise RuntimeError(f"端口 {port} 已被占用，请换一个端口") from exc
        sock.settimeout(0.25)
        self._sock = sock
        self._uptime_start = time.monotonic()

        time_period(True)
        self._running.set()
        cap = threading.Thread(target=self._capture_loop,
                               args=(device_index, rate, channels, packet_ms),
                               name="airwave-capture", daemon=True)
        cap.start()
        self._threads = [cap]

        if not self._ready.wait(6.0):
            self.stop()
            raise RuntimeError("打开音频设备超时，请刷新设备后重试")
        if self._open_error:
            err = self._open_error
            self.stop()
            raise RuntimeError(err)

        ctl = threading.Thread(target=self._control_loop, name="airwave-udp", daemon=True)
        snd = threading.Thread(target=self._send_loop, name="airwave-send", daemon=True)
        ctl.start()
        snd.start()
        self._threads.extend([ctl, snd])

        self._ips = local_ips()
        ips = self._ips
        self._log(f"音频引擎已启动：{self._rate} Hz / {self._channels}ch / {self._packet_ms}ms 包")
        self._log(f"UDP 监听 0.0.0.0:{port}，本机地址 {ips[0] if ips else '未知'}")
        self._log("等待手机连接…")

    # ---------------------------------------------------------------- capture
    def _capture_loop(self, device_index: int, rate: int, channels: int, packet_ms: int) -> None:
        p = None
        stream = None
        try:
            p = pyaudio.PyAudio()
            info = p.get_device_info_by_index(device_index)
            native_rate = int(info.get("defaultSampleRate") or 48000)
            native_ch = max(1, min(2, int(info.get("maxInputChannels") or 2)))
            candidates: List[Tuple[int, int]] = []
            for pair in ((rate, channels), (native_rate, channels),
                         (native_rate, native_ch), (48000, 2), (44100, 2)):
                r, c = int(pair[0]), max(1, int(pair[1]))
                if (r, c) not in candidates:
                    candidates.append((r, c))

            last_err: Optional[Exception] = None
            for r, c in candidates:
                frame_size = c * 2
                max_frames = max(64, (MAX_DATAGRAM_BYTES - AUDIO_HEADER_BYTES) // frame_size)
                requested = max(64, int(round(r * packet_ms / 1000.0)))
                frames = min(requested, max_frames)
                packet_bytes = frames * frame_size
                carry = bytearray()

                def on_audio(in_data, frame_count, time_info, status,
                             _pb=packet_bytes, _fs=frame_size, _ch=c):
                    if not self._running.is_set():
                        return (None, pyaudio.paComplete)
                    try:
                        carry.extend(in_data)
                        while len(carry) >= _pb:
                            chunk = bytes(carry[:_pb])
                            del carry[:_pb]
                            lvl = _rms_level(chunk, _ch)
                            self._level = lvl
                            self._levels.append(lvl)
                            try:
                                self._queue.put_nowait(chunk)
                            except queue.Full:
                                try:
                                    self._queue.get_nowait()
                                    self._dropped += 1
                                except queue.Empty:
                                    pass
                                try:
                                    self._queue.put_nowait(chunk)
                                except queue.Full:
                                    pass
                    except Exception:
                        self._callback_errors += 1
                    return (None, pyaudio.paContinue)

                try:
                    stream = p.open(
                        format=pyaudio.paInt16, channels=c, rate=r,
                        frames_per_buffer=frames, input=True,
                        input_device_index=device_index, stream_callback=on_audio,
                    )
                    self._rate, self._channels = r, c
                    self._frames, self._frame_size = frames, frame_size
                    self._packet_ms = round(frames * 1000.0 / r, 2)
                    if (r, c) != (rate, channels):
                        self._log(f"设备不支持 {rate}Hz/{channels}ch，已自动切换为 {r}Hz/{c}ch")
                    if frames < requested:
                        self._log(f"为避免 IP 分片，网络包已限制为 {frames} 帧 / "
                                  f"{self._packet_ms:.2f} ms（{packet_bytes + AUDIO_HEADER_BYTES} 字节）")
                    break
                except Exception as exc:
                    last_err = exc
                    stream = None
                    continue

            if stream is None:
                raise RuntimeError(f"无法打开采集设备：{last_err}")
            self._stream = stream
            self._ready.set()

            while self._running.is_set():
                if not stream.is_active():
                    raise RuntimeError("采集流意外停止，请重新开始推流")
                time.sleep(0.1)
        except Exception as exc:
            if self._running.is_set():
                self._open_error = str(exc)
                self._log(f"采集失败：{exc}")
                self._running.clear()
            else:
                self._open_error = str(exc)
        finally:
            self._ready.set()
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            self._stream = None
            try:
                if p is not None:
                    p.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------- send
    def _send_loop(self) -> None:
        while self._running.is_set():
            try:
                pcm = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            # Bound end-to-end latency: never transmit a backlog of stale audio.
            while self._queue.qsize() > 2:
                try:
                    self._queue.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    break

            seq = self._seq
            self._seq = (seq + 1) & 0xFFFFFFFF
            with self._lock:
                targets = list(self._clients.items())
            if not targets:
                continue
            pkt = build_audio(seq, pcm)
            sock = self._sock
            if sock is None:
                break
            for addr, client in targets:
                try:
                    sock.sendto(pkt, addr)
                    client.packets += 1
                    self._packets_sent += 1
                    self._bytes_sent += len(pkt)
                except OSError:
                    self._send_errors += 1

    # ---------------------------------------------------------------- control
    def _control_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        last_meta = 0.0
        last_prune = 0.0
        while self._running.is_set():
            now = time.monotonic()
            if now - last_meta >= META_INTERVAL:
                last_meta = now
                self._broadcast_meta()
            if now - last_prune >= 1.0:
                last_prune = now
                self._prune(now)
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                if not self._running.is_set():
                    break
                continue
            kind = parse_control(data)
            if kind == "hello":
                self._register(addr)
            elif kind == "bye":
                self._remove(addr, "手机主动断开")

    def _register(self, addr: Tuple[str, int]) -> None:
        now = time.monotonic()
        with self._lock:
            client = self._clients.get(addr)
            new = client is None
            if client is None:
                client = Client(addr=addr, first_seen=now, last_seen=now)
                self._clients[addr] = client
            client.last_seen = now
            client.hellos += 1
            count = len(self._clients)
        # Always answer a HELLO with metadata: this is the recovery path when a
        # META datagram is lost or when the PC restarted the stream.
        self._send_meta(addr)
        if new:
            self._log(f"手机接入 {addr[0]}:{addr[1]}（{count} 台在线）")

    def _remove(self, addr: Tuple[str, int], reason: str) -> None:
        with self._lock:
            existed = self._clients.pop(addr, None) is not None
            count = len(self._clients)
        if existed:
            self._log(f"{reason} {addr[0]}:{addr[1]}（{count} 台在线）")

    def _prune(self, now: float) -> None:
        dead: List[Tuple[str, int]] = []
        with self._lock:
            for addr, client in self._clients.items():
                if now - client.last_seen > CLIENT_TIMEOUT:
                    dead.append(addr)
            for addr in dead:
                self._clients.pop(addr, None)
        for addr in dead:
            self._log(f"手机已离线 {addr[0]}:{addr[1]}")

    def _meta_packet(self) -> Optional[bytes]:
        if not self._rate:
            return None
        return build_meta(self._rate, self._channels, self._frames,
                          self._stream_id, self._server_name)

    def _send_meta(self, addr: Tuple[str, int]) -> None:
        pkt = self._meta_packet()
        if pkt is None or self._sock is None:
            return
        try:
            self._sock.sendto(pkt, addr)
        except OSError:
            pass

    def _broadcast_meta(self) -> None:
        pkt = self._meta_packet()
        if pkt is None or self._sock is None:
            return
        with self._lock:
            targets = list(self._clients.keys())
        for addr in targets:
            try:
                self._sock.sendto(pkt, addr)
            except OSError:
                pass

    # ------------------------------------------------------------------- stop
    def stop(self) -> None:
        was_running = self._running.is_set()
        self._running.clear()
        threads = list(self._threads)
        self._threads = []
        for t in threads:
            if t is threading.current_thread():
                continue
            t.join(timeout=2.5)
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._lock:
            had = len(self._clients)
            self._clients.clear()
        self._stream = None
        self._level = 0.0
        time_period(False)
        if was_running:
            self._log(f"推流已停止（断开 {had} 台设备）")

    # --------------------------------------------------------------- snapshot
    def snapshot(self) -> Snapshot:
        now = time.monotonic()
        with self._lock:
            clients = [
                {
                    "ip": addr[0], "port": addr[1],
                    "connected": max(0.0, now - c.first_seen),
                    "last_seen": max(0.0, now - c.last_seen),
                    "packets": c.packets,
                }
                for addr, c in self._clients.items()
            ]
        clients.sort(key=lambda c: c["connected"], reverse=True)
        return Snapshot(
            running=self._running.is_set(),
            ready=bool(self._rate),
            rate=self._rate,
            channels=self._channels,
            packet_ms=self._packet_ms,
            port=self._port,
            clients=clients,
            level=self._level,
            levels=list(self._levels),
            packets_sent=self._packets_sent,
            bytes_sent=self._bytes_sent,
            dropped=self._dropped,
            send_errors=self._send_errors,
            uptime=(now - self._uptime_start) if self._uptime_start else 0.0,
            stream_id=self._stream_id,
            device_name=self._device_name,
            ips=list(self._ips),
            queue_depth=self._queue.qsize(),
            error=self._open_error,
        )

    # ------------------------------------------------------------------ misc
    @property
    def running(self) -> bool:
        return self._running.is_set()

    @property
    def server_name(self) -> str:
        return self._server_name
