# -*- coding: utf-8 -*-
"""15-second receive soak: checks sequence continuity, cadence and drops."""
from __future__ import annotations

import json
import socket
import statistics
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from airwave.protocol import AUDIO, META  # noqa: E402
from airwave.server import AudioServer  # noqa: E402

PORT = 13667
SECONDS = 16


def main() -> int:
    dev = AudioServer.list_devices()[0]
    logs = []
    srv = AudioServer(lambda m: logs.append(m))
    srv.start(dev.index, dev.name, PORT, 48000, 2, 7)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2)
    stop = False

    def hello():
        while not stop:
            try:
                sock.sendto(b"HELLO", ("127.0.0.1", PORT))
            except OSError:
                pass
            time.sleep(0.5)

    threading.Thread(target=hello, daemon=True).start()
    times, seqs, sizes = [], [], []
    meta = None
    deadline = time.monotonic() + SECONDS
    while time.monotonic() < deadline:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        if data[0] == META:
            ln = struct.unpack(">H", data[1:3])[0]
            meta = json.loads(data[3:3 + ln])
        elif data[0] == AUDIO:
            times.append(time.monotonic())
            seqs.append(struct.unpack(">I", data[1:5])[0])
            sizes.append(len(data) - 5)
    stop = True
    snap = srv.snapshot()
    srv.stop()
    sock.close()

    gaps = sum(1 for a, b in zip(seqs, seqs[1:]) if b != (a + 1) & 0xFFFFFFFF)
    deltas = [(b - a) * 1000 for a, b in zip(times, times[1:])]
    print("meta", meta)
    print(f"packets={len(seqs)} gaps={gaps} sizes={sorted(set(sizes))}")
    print(f"interval mean={statistics.mean(deltas):.2f}ms "
          f"p95={sorted(deltas)[int(len(deltas)*0.95)]:.2f}ms max={max(deltas):.2f}ms")
    print(f"server packets_sent={snap.packets_sent} dropped={snap.dropped} "
          f"send_errors={snap.send_errors} queue={snap.queue_depth}")
    ok = gaps == 0 and snap.send_errors == 0 and len(seqs) > 1500
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
