# -*- coding: utf-8 -*-
"""AirWave — Windows 端入口。

开发运行:  python app.py
打包:      pyinstaller AirWaveServer.spec
诊断:      python app.py --diagnose-out diag.txt
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from airwave.paths import resource_path
from airwave.winutil import set_app_user_model_id


def _write_diagnostics(out_path: str) -> int:
    from airwave.server import AudioServer, local_ips

    lines = ["AirWave diagnostics", f"python={sys.version}", f"frozen={getattr(sys, 'frozen', False)}"]
    try:
        lines.append("ips=" + ", ".join(local_ips()))
    except Exception as exc:
        lines.append(f"ips error: {exc}")
    try:
        for d in AudioServer.list_devices():
            lines.append(f"device {d.index}: {d.display} | {d.detail} | default={d.is_default}")
    except Exception as exc:
        lines.append(f"device error: {exc}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return 0


def _install_excepthook() -> None:
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AirWave"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    log_file = log_dir / "error.log"

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except Exception:
            pass
        try:
            QMessageBox.critical(None, "AirWave 发生错误",
                                 f"{exc}\n\n详细信息已写入:\n{log_file}")
        except Exception:
            pass

    sys.excepthook = hook


def _dark_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#0B1423"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#E9F0FB"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#0A111E"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#0E1929"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#E9F0FB"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#111D30"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#C9D6EA"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#2C5A96"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0E1A2C"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#DCE7F7"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#55647D"))
    return pal


def main() -> int:
    if "--diagnose-out" in sys.argv:
        i = sys.argv.index("--diagnose-out")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "airwave-diagnostics.txt"
        return _write_diagnostics(out)

    set_app_user_model_id("AirWave.Server.2")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("AirWave")
    app.setOrganizationName("AirWave")
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setWindowIcon(QIcon(resource_path("assets/app.ico")))

    font = QFont("Microsoft YaHei UI", 9)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    _install_excepthook()

    # Packaged-build smoke test: render the window, save a PNG, exit.
    if "--smoke-test" in sys.argv:
        i = sys.argv.index("--smoke-test")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "airwave-smoke.png"
        from airwave.main_window import MainWindow

        window = MainWindow()
        window.show()

        def _grab():
            window.grab().save(out)
            app.quit()

        QTimer.singleShot(1800, _grab)
        return app.exec()

    # Single instance: a second launch just brings the existing window forward.
    probe = QLocalSocket()
    probe.connectToServer("AirWave.Server")
    if probe.waitForConnected(250):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return 0
    QLocalServer.removeServer("AirWave.Server")
    local = QLocalServer()
    local.listen("AirWave.Server")

    from airwave.main_window import MainWindow

    window = MainWindow()
    local.newConnection.connect(window._show_window)
    window.show()
    code = app.exec()
    local.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
