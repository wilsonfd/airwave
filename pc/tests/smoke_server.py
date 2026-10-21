# -*- coding: utf-8 -*-
"""End-to-end protocol/pacing test without an iPhone.

Run: python tests/smoke_server.py [packet_ms]
It registers a fake phone over UDP, captures 2 seconds of audio, and checks
metadata, sequence continuity, packet size and send cadence.
"""
from __future__ import annotations

import json
import socket
import statistics
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from airwave.protocol import AUDIO, META  # noqa: E402
from airwave.server import AudioServer  # noqa: E402

PORT = 13999


def main() -> int:
    packet_ms = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    logs = []
    devices = AudioServer.list_devices()
    print(f"devices: {len(devices)}")
    for d in devices[:8]:
        print(f"  {d.index:>3} {d.display}  {d.detail}  default={d.is_default}")
    if not devices:
        print("NO DEVICES")
        return 2
    dev = devices[0]
    server = AudioServer(lambda m: (logs.append(m), print("  [log]", m)))
    server.start(dev.index, dev.name, PORT, rate=dev.rate,
                 channels=dev.channels, packet_ms=packet_ms)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    sock.sendto(b"HELLO", ("127.0.0.1", PORT))

    meta = None
    audio = []
    t_end = time.monotonic() + 2.2
    while time.monotonic() < t_end:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            break
        if not data:
            continue
        if data[0] == META:
            ln = struct.unpack(">H", data[1:3])[0]
            meta = json.loads(data[3:3 + ln])
            print("META", meta)
        elif data[0] == AUDIO:
            seq = struct.unpack(">I", data[1:5])[0]
            audio.append((time.monotonic(), seq, len(data) - 5))

    sock.sendto(b"BYE", ("127.0.0.1", PORT))
    time.sleep(0.3)
    time.sleep(0.5)
    snap = server.snapshot()
    sock.close()

    ok = True
    if meta is None:
        print("FAIL: no META")
        return 3
    expected_frames = meta["packet_frames"]
    actual_ms = expected_frames * 1000.0 / meta["rate"]
    if expected_frames * meta["channels"] * 2 + 5 > 1400:
        print(f"FAIL: datagram too large ({expected_frames} frames)")
        ok = False
    if abs(meta["packet_ms"] - actual_ms) > 0.02:
        print(f"FAIL: packet_ms {meta['packet_ms']} != {actual_ms}")
        ok = False
    if actual_ms > packet_ms + 0.01:
        print(f"FAIL: actual {actual_ms} exceeds requested {packet_ms}")
        ok = False
    if not audio:
        print("FAIL: no audio")
        return 4

    sizes = {a[2] for a in audio}
    expected_size = expected_frames * meta["channels"] * 2
    if sizes != {expected_size}:
        print(f"FAIL: sizes {sizes} expected {expected_size}")
        ok = False
    seqs = [a[1] for a in audio]
    gaps = sum(1 for a, b in zip(seqs, seqs[1:]) if b != (a + 1) & 0xFFFFFFFF)
    if gaps:
        print(f"FAIL: {gaps} sequence gaps")
        ok = False
    times = [a[0] for a in audio]
    deltas = [(b - a) * 1000 for a, b in zip(times, times[1:])]
    print(f"audio packets={len(audio)} size={expected_size} "
          f"mean={statistics.mean(deltas):.2f}ms "
          f"p95={sorted(deltas)[int(len(deltas) * 0.95)]:.2f}ms "
          f"max={max(deltas):.2f}ms gaps={gaps}")
    if not (actual_ms * 0.7 <= statistics.mean(deltas) <= actual_ms * 1.3):
        print("FAIL: cadence out of range")
        ok = False
    if snap.clients:
        print(f"FAIL: BYE did not remove client: {snap.clients}")
        ok = False

    # Reconnect must work without restarting the server.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    sock.sendto(b"HELLO", ("127.0.0.1", PORT))
    got_meta = got_audio = False
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not (got_meta and got_audio):
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            break
        if data[0] == META:
            got_meta = True
        elif data[0] == AUDIO:
            got_audio = True
    sock.close()
    print(f"reconnect meta={got_meta} audio={got_audio}")
    ok = ok and got_meta and got_audio
    server.stop()
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
