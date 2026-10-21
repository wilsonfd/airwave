# -*- coding: utf-8 -*-
"""Start the engine from the UI, play a quiet tone, register a fake phone,
and capture the running-state screenshot."""
from __future__ import annotations

import math
import os
import socket
import struct
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from airwave.main_window import MainWindow  # noqa: E402

PORT = 13666


def tone() -> None:
    try:
        import pyaudiowpatch as pa
        p = pa.PyAudio()
        s = p.open(format=pa.paInt16, channels=2, rate=48000, output=True,
                   frames_per_buffer=480)
        frames = 480
        phase = 0.0
        step = 2 * math.pi * 440 / 48000
        for _ in range(220):  # ~2.2 s
            buf = bytearray()
            for _ in range(frames):
                v = int(1800 * math.sin(phase))
                phase += step
                buf += struct.pack("<hh", v, v)
            s.write(bytes(buf))
        s.stop_stream()
        s.close()
        p.terminate()
    except Exception as exc:
        print("tone failed", exc)


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    out = Path(__file__).resolve().parent / "shot_running.png"
    state = {"started": False, "sock": None}

    def start():
        if not w._devices:
            QTimer.singleShot(300, start)
            return
        w.port_edit.setText(str(PORT))
        w._start_async()
        state["started"] = True
        QTimer.singleShot(1800, client)

    def client():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        state["sock"] = sock

        def hello_loop():
            for _ in range(20):
                try:
                    sock.sendto(b"HELLO", ("127.0.0.1", PORT))
                except OSError:
                    pass
                import time
                time.sleep(0.4)

        threading.Thread(target=hello_loop, daemon=True).start()
        threading.Thread(target=tone, daemon=True).start()
        QTimer.singleShot(2600, snap)

    def snap():
        w.grab().save(str(out))
        print(f"saved {out}", "running=", w.engine.running)
        try:
            if state["sock"]:
                state["sock"].close()
        except OSError:
            pass
        w._stop_async()
        QTimer.singleShot(1200, app.quit)

    QTimer.singleShot(1600, start)
    QTimer.singleShot(15000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

