# -*- coding: utf-8 -*-
"""Render the main window offscreen and save a PNG for visual review."""
from __future__ import annotations

import os
import sys
from pathlib import Path

if os.environ.get("AIRWAVE_OFFSCREEN") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from airwave.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.resize(1160, 830)
    w.show()
    out = Path(__file__).resolve().parent / "shot_main.png"

    def snap():
        w.grab().save(str(out))
        print(f"saved {out} {w.size().width()}x{w.size().height()}")
        app.quit()

    QTimer.singleShot(1800, snap)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
