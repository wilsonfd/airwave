# -*- coding: utf-8 -*-
"""AirWave main window."""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QIntValidator, QKeySequence, QLinearGradient,
    QPainter, QPixmap, QRadialGradient, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import theme
from .paths import resource_path
from .server import AudioServer, DeviceInfo, Snapshot
from .widgets import (
    ClientListWidget, LogView, MetricCard, PowerButton, StatusPill, WaveformWidget,
)
from .winutil import add_firewall_rule, enable_dark_title_bar, firewall_rule_exists


class MainWindow(QWidget):
    log_signal = Signal(str)
    devices_signal = Signal(object)
    start_signal = Signal(bool, str)
    stop_signal = Signal()
    firewall_signal = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AirWave · 局域网音频推流")
        self.setWindowIcon(QIcon(resource_path("assets/app.ico")))
        self.setMinimumSize(1020, 760)
        self.resize(1160, 820)

        self.settings = QSettings("AirWave", "Server")
        self.engine = AudioServer(self._emit_log)
        self._devices: List[DeviceInfo] = []
        self._busy = False
        self._scanning = False
        self._quitting = False
        self._centered = False
        self._was_running = False
        self._failure_handled = False
        self._ip = ""
        self._firewall_checking = False
        self._firewall_ok: Optional[bool] = None
        self._tray: Optional[QSystemTrayIcon] = None

        self.log_signal.connect(self._append_log)
        self.devices_signal.connect(self._on_devices)
        self.start_signal.connect(self._on_start_done)
        self.stop_signal.connect(self._on_stop_done)
        self.firewall_signal.connect(self._on_firewall_checked)

        self._build_ui()
        self._restore_settings()
        self._setup_tray()
        self._stats = QTimer(self)
        self._stats.setInterval(100)
        self._stats.timeout.connect(self._poll)
        self._stats.start()

        self._append_log("AirWave 2.0 已就绪")
        self._append_log("正在扫描音频设备…")
        QTimer.singleShot(80, self._refresh_devices)
        QTimer.singleShot(600, self._check_firewall)

        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._refresh_devices)

    # ------------------------------------------------------------------ build
    def _build_ui(self) -> None:
        self.setStyleSheet(theme.QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 14)
        root.setSpacing(12)

        # Header -----------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        pix = QPixmap(resource_path("assets/logo.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(46, 46, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("A")
            logo.setStyleSheet("font-size:28px;font-weight:800;color:#6AA9FF;")
        logo.setFixedSize(48, 48)
        header.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("AirWave")
        t.setObjectName("AppTitle")
        s = QLabel("局域网 · 无损音频串流")
        s.setObjectName("Subtitle")
        titles.addWidget(t)
        titles.addWidget(s)
        header.addLayout(titles)
        header.addStretch()

        self.pill = StatusPill()
        self.pill.set_state("未运行", theme.MUTED, False)
        header.addWidget(self.pill, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.ip_btn = QPushButton("获取 IP…")
        self.ip_btn.setObjectName("ChipBtn")
        self.ip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ip_btn.setFixedHeight(28)
        self.ip_btn.setToolTip("点击复制局域网地址")
        self.ip_btn.clicked.connect(self._copy_ip)
        header.addWidget(self.ip_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        # Body -------------------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(14)

        left = QFrame()
        left.setObjectName("Card")
        left.setFixedWidth(408)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(20, 16, 20, 16)
        ll.setSpacing(9)

        ll.addLayout(self._section("音频来源", "SOURCE"))
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        self.device_combo = QComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        dev_row.addWidget(self.device_combo, 1)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("GhostBtn")
        self.refresh_btn.setFixedWidth(58)
        self.refresh_btn.clicked.connect(self._refresh_devices)
        dev_row.addWidget(self.refresh_btn)
        ll.addLayout(dev_row)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(8)
        self.kind_badge = QLabel("系统声音")
        self.kind_badge.setObjectName("KindSystem")
        self.kind_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_row.addWidget(self.kind_badge)
        self.detail_label = QLabel("—")
        self.detail_label.setObjectName("Detail")
        detail_row.addWidget(self.detail_label)
        detail_row.addStretch()
        ll.addLayout(detail_row)

        ll.addWidget(self._divider())
        ll.addLayout(self._section("传输设置", "STREAM"))

        fields = QHBoxLayout()
        fields.setSpacing(8)
        self.rate_combo = QComboBox()
        self.rate_combo.addItem("48 kHz", 48000)
        self.rate_combo.addItem("44.1 kHz", 44100)
        self.rate_combo.addItem("96 kHz", 96000)
        self.rate_combo.currentIndexChanged.connect(self._on_format_changed)
        fields.addWidget(self._field("采样率", self.rate_combo), 1)

        self.ch_combo = QComboBox()
        self.ch_combo.addItem("立体声", 2)
        self.ch_combo.addItem("单声道", 1)
        self.ch_combo.currentIndexChanged.connect(self._on_format_changed)
        fields.addWidget(self._field("声道", self.ch_combo), 1)

        self.packet_combo = QComboBox()
        self.packet_combo.addItem("7 ms · 推荐", 7)
        self.packet_combo.addItem("5 ms · 低延迟", 5)
        self.packet_combo.currentIndexChanged.connect(self._on_format_changed)
        fields.addWidget(self._field("音频包", self.packet_combo), 1)
        ll.addLayout(fields)

        port_box = QVBoxLayout()
        port_box.setSpacing(4)
        pl = QLabel("UDP 端口")
        pl.setObjectName("FieldLabel")
        port_box.addWidget(pl)
        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        self.port_edit = QLineEdit("13666")
        self.port_edit.setValidator(QIntValidator(1024, 65535, self))
        self.port_edit.setFixedHeight(36)
        self.port_edit.editingFinished.connect(self._on_port_changed)
        port_row.addWidget(self.port_edit, 1)
        self.firewall_btn = QPushButton("放行")
        self.firewall_btn.setObjectName("GhostBtn")
        self.firewall_btn.setFixedWidth(58)
        self.firewall_btn.setToolTip("添加 Windows 防火墙入站规则（需要管理员确认）")
        self.firewall_btn.clicked.connect(self._allow_firewall)
        port_row.addWidget(self.firewall_btn)
        port_box.addLayout(port_row)
        self.firewall_label = QLabel("防火墙：检测中…")
        self.firewall_label.setObjectName("Detail")
        port_box.addWidget(self.firewall_label)
        ll.addLayout(port_box)

        info = QFrame()
        info.setObjectName("InfoBox")
        il = QVBoxLayout(info)
        il.setContentsMargins(12, 10, 12, 10)
        hint = QLabel("默认抓取系统正在播放的声音。若某个 App 抓不到：安装 VB-Cable，"
                      "把 Windows 输出设为 CABLE Input，再在上方选择 CABLE Output。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        il.addWidget(hint)
        ll.addWidget(info)

        ll.addLayout(self._section("手机连接", "3 STEPS"))
        steps = QFrame()
        steps.setObjectName("SubCard")
        sl = QVBoxLayout(steps)
        sl.setContentsMargins(12, 9, 12, 9)
        sl.setSpacing(5)
        for num, text in (
            ("01", "手机与电脑连接同一个 WiFi"),
            ("02", "打开 AirWave，填写上方 IP 和端口"),
            ("03", "点连接，电脑放什么手机就响什么"),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            n = QLabel(num)
            n.setStyleSheet(f"color:{theme.ACCENT};font-family:Consolas;font-size:9px;font-weight:700;")
            n.setFixedWidth(18)
            t = QLabel(text)
            t.setStyleSheet(f"color:{theme.MUTED};font-size:10px;")
            row.addWidget(n)
            row.addWidget(t, 1)
            sl.addLayout(row)
        ll.addWidget(steps)

        ll.addStretch()
        ver = QLabel("AirWave 2.0.0   ·   仅局域网   ·   只传音频")
        ver.setObjectName("Version")
        ll.addWidget(ver)
        body.addWidget(left)

        right = QFrame()
        right.setObjectName("Card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(5)

        rh = QHBoxLayout()
        rsec = QLabel("推流控制")
        rsec.setObjectName("Section")
        rh.addWidget(rsec)
        rh.addStretch()
        chip = QLabel("UDP  ·  PCM 16-bit")
        chip.setObjectName("Chip")
        rh.addWidget(chip)
        rl.addLayout(rh)

        self.power = PowerButton()
        self.power.clicked.connect(self._toggle)
        rl.addWidget(self.power, alignment=Qt.AlignmentFlag.AlignHCenter)

        wh = QHBoxLayout()
        wl = QLabel("实时电平")
        wl.setObjectName("Section")
        wh.addWidget(wl)
        wh.addStretch()
        self.level_label = QLabel("—")
        self.level_label.setObjectName("Chip")
        wh.addWidget(self.level_label)
        rl.addLayout(wh)

        self.wave = WaveformWidget()
        rl.addWidget(self.wave)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.m_clients = MetricCard("在线设备", "0", "台手机")
        self.m_packets = MetricCard("已发送", "0", "音频包")
        self.m_bitrate = MetricCard("实时码率", "—", "每台设备")
        self.m_uptime = MetricCard("运行时长", "00:00", "本次推流")
        for m in (self.m_clients, self.m_packets, self.m_bitrate, self.m_uptime):
            metrics.addWidget(m, 1)
        rl.addLayout(metrics)

        ch = QHBoxLayout()
        csec = QLabel("已连接设备")
        csec.setObjectName("Section")
        ch.addWidget(csec)
        ch.addStretch()
        self.client_count = QLabel("0 台")
        self.client_count.setObjectName("Chip")
        ch.addWidget(self.client_count)
        rl.addLayout(ch)

        self.clients = ClientListWidget()
        rl.addWidget(self.clients)
        rl.addStretch(1)
        body.addWidget(right, 1)
        root.addLayout(body, 1)

        # Log --------------------------------------------------------------
        log_card = QFrame()
        log_card.setObjectName("Card")
        lc = QVBoxLayout(log_card)
        lc.setContentsMargins(16, 10, 16, 12)
        lc.setSpacing(6)
        lh = QHBoxLayout()
        lsec = QLabel("运行日志")
        lsec.setObjectName("Section")
        lh.addWidget(lsec)
        lh.addStretch()
        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("GhostBtn")
        copy_btn.setFixedHeight(26)
        copy_btn.clicked.connect(self._copy_log)
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("GhostBtn")
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(lambda: self.log_view.clear())
        lh.addWidget(copy_btn)
        lh.addWidget(clear_btn)
        lc.addLayout(lh)
        self.log_view = LogView()
        self.log_view.setFixedHeight(88)
        lc.addWidget(self.log_view)
        root.addWidget(log_card)

        self._set_controls_enabled(True)

    def _section(self, title: str, hint: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lab = QLabel(title)
        lab.setObjectName("Section")
        row.addWidget(lab)
        row.addStretch()
        h = QLabel(hint)
        h.setObjectName("SectionHint")
        row.addWidget(h)
        return row

    def _field(self, label: str, widget: QWidget) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lab = QLabel(label)
        lab.setObjectName("FieldLabel")
        lay.addWidget(lab)
        lay.addWidget(widget)
        return box

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    # ------------------------------------------------------------------ tray
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self.windowIcon(), self)
        self._tray.setToolTip("AirWave · 局域网音频推流")
        menu = QMenu(self)
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_window)
        self.tray_toggle = QAction("开始推流", self)
        self.tray_toggle.triggered.connect(self._toggle)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
        menu.addAction(self.tray_toggle)
        menu.addSeparator()
        menu.addAction(quit_action)
        menu.aboutToShow.connect(self._update_tray_menu)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _update_tray_menu(self) -> None:
        self.tray_toggle.setText("停止推流" if self.engine.running else "开始推流")

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # --------------------------------------------------------------- devices
    def _refresh_devices(self) -> None:
        if self._scanning or self.engine.running or self._busy:
            return
        self._scanning = True
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("扫描…")
        threading.Thread(target=self._scan_worker, name="airwave-scan", daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            devices = AudioServer.list_devices()
        except Exception:
            devices = []
        self.devices_signal.emit(devices)

    def _on_devices(self, devices: list) -> None:
        self._scanning = False
        self.refresh_btn.setText("刷新")
        self.refresh_btn.setEnabled(not self.engine.running and not self._busy)
        self._devices = list(devices)
        current_sig = ""
        cur = self.device_combo.currentData()
        if isinstance(cur, DeviceInfo):
            current_sig = self._device_sig(cur)
        saved_sig = str(self.settings.value("device_sig", "") or "")
        target = current_sig or saved_sig

        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for d in self._devices:
            self.device_combo.addItem(d.display, d)
        if self._devices:
            idx = 0
            for i, d in enumerate(self._devices):
                if target and self._device_sig(d) == target:
                    idx = i
                    break
            self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)

        if self._devices:
            self._on_device_changed(self.device_combo.currentIndex())
            self._append_log(f"找到 {len(self._devices)} 个音频设备")
        else:
            self.power.setEnabled(False)
            self.pill.set_state("未就绪", theme.AMBER, False)
            self._append_log("没有找到音频设备，请检查声卡驱动")

    @staticmethod
    def _device_sig(d: DeviceInfo) -> str:
        return f"{d.name}|{d.kind}"

    def _on_device_changed(self, _index: int) -> None:
        d = self.device_combo.currentData()
        if not isinstance(d, DeviceInfo):
            return
        ridx = self.rate_combo.findData(d.rate)
        if ridx < 0:
            self.rate_combo.addItem(f"{d.rate / 1000:g} kHz", d.rate)
            ridx = self.rate_combo.count() - 1
        self.rate_combo.setCurrentIndex(ridx)
        cidx = self.ch_combo.findData(min(2, max(1, d.channels)))
        if cidx >= 0:
            self.ch_combo.setCurrentIndex(cidx)

        self.kind_badge.setText(d.kind_label)
        self.kind_badge.setObjectName(
            {"system": "KindSystem", "virtual": "KindVirtual", "input": "KindInput"}[d.kind])
        self.kind_badge.style().unpolish(self.kind_badge)
        self.kind_badge.style().polish(self.kind_badge)
        self._update_detail()
        self.settings.setValue("device_sig", self._device_sig(d))
        self.power.setEnabled(True)

    def _on_format_changed(self, _index: int) -> None:
        self._update_detail()
        self._save_settings()

    def _update_detail(self) -> None:
        d = self.device_combo.currentData()
        if not isinstance(d, DeviceInfo):
            return
        rate = int(self.rate_combo.currentData() or d.rate)
        ch = int(self.ch_combo.currentData() or d.channels)
        pm = int(self.packet_combo.currentData() or 7)
        frame_size = max(1, ch * 2)
        max_frames = max(64, (1400 - 5) // frame_size)
        frames = min(max(64, round(rate * pm / 1000)), max_frames)
        actual_ms = frames * 1000.0 / rate
        self.detail_label.setText(
            f"{rate} Hz · {'立体声' if ch >= 2 else '单声道'} · "
            f"{actual_ms:.1f} ms 包 / {frames * frame_size + 5} B")

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in (self.device_combo, self.refresh_btn, self.rate_combo,
                  self.ch_combo, self.packet_combo, self.port_edit, self.firewall_btn):
            w.setEnabled(enabled)
        if enabled:
            self.power.setEnabled(bool(self._devices))

    # ------------------------------------------------------------------ start
    def _toggle(self) -> None:
        if self._busy:
            return
        if self.engine.running:
            self._stop_async()
        else:
            self._start_async()

    def _start_async(self) -> None:
        d = self.device_combo.currentData()
        if not isinstance(d, DeviceInfo):
            self._append_log("请先选择音频设备")
            return
        try:
            port = int(self.port_edit.text())
        except ValueError:
            port = 0
        if not (1024 <= port <= 65535):
            self._append_log("端口需在 1024–65535 之间")
            self.port_edit.setFocus()
            return
        rate = int(self.rate_combo.currentData() or 48000)
        ch = int(self.ch_combo.currentData() or 2)
        pm = int(self.packet_combo.currentData() or 10)
        self._save_settings()
        self._failure_handled = False
        self._set_busy(True, "正在启动…")
        self._append_log(f"正在启动：{d.clean_name} · {rate} Hz / {ch}ch / {pm} ms")
        threading.Thread(target=self._start_worker, args=(d, port, rate, ch, pm),
                         name="airwave-start", daemon=True).start()

    def _start_worker(self, d: DeviceInfo, port: int, rate: int, ch: int, pm: int) -> None:
        try:
            self.engine.start(d.index, d.name, port, rate=rate, channels=ch, packet_ms=pm)
            self.start_signal.emit(True, "")
        except Exception as exc:
            self.start_signal.emit(False, str(exc))

    def _on_start_done(self, ok: bool, err: str) -> None:
        self._set_busy(False)
        if ok:
            self._was_running = True
            self.power.set_running(True)
            self.power.setEnabled(True)
            self.pill.set_state("运行中", theme.MINT, True)
            self._set_controls_enabled(False)
            self._append_log("推流已开始，手机连上后会自动播放")
        else:
            self.power.set_running(False)
            self.power.set_idle()
            self.pill.set_state("启动失败", theme.RED, False)
            self._append_log(f"启动失败：{err}")
            self._set_controls_enabled(True)
            QMessageBox.warning(self, "无法开始推流", err or "未知错误")

    def _stop_async(self) -> None:
        self._set_busy(True, "正在停止…")
        threading.Thread(target=self._stop_worker, name="airwave-stop", daemon=True).start()

    def _stop_worker(self) -> None:
        try:
            self.engine.stop()
        finally:
            self.stop_signal.emit()

    def _on_stop_done(self) -> None:
        self._was_running = False
        self._set_busy(False)
        self.power.set_running(False)
        self.power.set_idle()
        self.power.setEnabled(bool(self._devices))
        self.pill.set_state("未运行", theme.MUTED, False)
        self._set_controls_enabled(True)
        self.wave.set_running(False)
        self.level_label.setText("—")
        self.clients.set_clients([])
        self.m_clients.set_value("0", "台手机")
        self.m_packets.set_value("0", "音频包")
        self.m_bitrate.set_value("—", "每台设备")
        self.m_uptime.set_value("00:00", "本次推流")

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        if busy:
            self.power.set_busy(text or "请稍候…")
            self.power.setEnabled(False)
            self._set_controls_enabled(False)
        else:
            self.power.setEnabled(True)
            self._set_controls_enabled(True)

    # ------------------------------------------------------------------- poll
    def _poll(self) -> None:
        if self.engine is None:
            return
        snap = self.engine.snapshot()
        if self._was_running and not snap.running and not self._busy and not self._failure_handled:
            self._failure_handled = True
            self._was_running = False
            self._append_log(f"推流中断：{snap.error or '采集设备已停止'}")
            self.pill.set_state("异常", theme.RED, False)
            self._stop_async()
            return

        running = snap.running
        if not self._busy:
            if running:
                self.pill.set_state("运行中", theme.MINT, True)
                self.power.set_running(True)
            elif snap.error:
                self.pill.set_state("异常", theme.RED, False)
                self.power.set_running(False)
            else:
                self.pill.set_state("未运行", theme.MUTED, False)
                self.power.set_running(False)

        self.wave.set_running(running)
        if running:
            self.wave.set_level(snap.level)
            self.level_label.setText(f"{int(snap.level * 100)}%")
        else:
            self.level_label.setText("—")

        n = len(snap.clients)
        self.m_clients.set_value(str(n), "台手机")
        self.m_packets.set_value(self._fmt_int(snap.packets_sent), "音频包")
        if running and n:
            mbps = snap.rate * snap.channels * 2 * 8 / 1_000_000
            self.m_bitrate.set_value(f"{mbps:.2f} Mbps", f"每台 · {snap.packet_ms:.1f}ms 包")
        else:
            self.m_bitrate.set_value("—", "每台设备")
        self.m_uptime.set_value(self._fmt_uptime(snap.uptime), "本次推流")
        self.client_count.setText(f"{n} 台")
        self.clients.set_clients(snap.clients)

        if snap.ips:
            ip = snap.ips[0]
            if ip != self._ip:
                self._ip = ip
                self.ip_btn.setText(f"{ip}  复制")
        elif not self._ip:
            self.ip_btn.setText("未获取 IP")

    @staticmethod
    def _fmt_int(value: int) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1000:
            return f"{value / 1000:.1f}k"
        return str(value)

    @staticmethod
    def _fmt_uptime(sec: float) -> str:
        sec = int(max(0, sec))
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    # -------------------------------------------------------------- firewall
    def _on_port_changed(self) -> None:
        self._save_settings()
        self.firewall_label.setText("防火墙：检测中…")
        self.firewall_btn.setEnabled(True)
        self._check_firewall()

    def _check_firewall(self) -> None:
        if self._firewall_checking:
            return
        try:
            port = int(self.port_edit.text())
        except ValueError:
            return
        self._firewall_checking = True
        self._firewall_ok = None
        self.firewall_label.setText("防火墙：检测中…")
        threading.Thread(target=self._firewall_worker, args=(port,),
                         name="airwave-fw", daemon=True).start()

    def _firewall_worker(self, port: int) -> None:
        ok = firewall_rule_exists(port)
        self.firewall_signal.emit(ok)

    def _on_firewall_checked(self, ok: bool) -> None:
        self._firewall_checking = False
        self._firewall_ok = ok
        if ok:
            self.firewall_label.setText("防火墙：已放行 UDP 入站")
            self.firewall_label.setStyleSheet(f"color:{theme.MINT};")
            self.firewall_btn.setText("已放行")
            self.firewall_btn.setEnabled(False)
        else:
            self.firewall_label.setText("防火墙：未放行，手机可能连不上")
            self.firewall_label.setStyleSheet(f"color:{theme.AMBER};")
            self.firewall_btn.setText("放行")
            self.firewall_btn.setEnabled(True)

    def _allow_firewall(self) -> None:
        try:
            port = int(self.port_edit.text())
        except ValueError:
            return
        self._append_log(f"正在为 UDP {port} 添加防火墙规则，请在 UAC 窗口确认…")
        if add_firewall_rule(port):
            self._append_log("已提交防火墙规则，1.5 秒后复查")
            QTimer.singleShot(1500, self._check_firewall)
        else:
            self._append_log("未添加防火墙规则（可能取消了管理员授权）")

    # ---------------------------------------------------------------- actions
    def _copy_ip(self) -> None:
        if not self._ip:
            return
        QApplication.clipboard().setText(self._ip)
        self.ip_btn.setText("已复制 ✓")
        QTimer.singleShot(1400, lambda: self.ip_btn.setText(f"{self._ip}  复制"))

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self._append_log("日志已复制到剪贴板")

    def _emit_log(self, msg: str) -> None:
        self.log_signal.emit(str(msg))

    def _append_log(self, msg: str) -> None:
        self.log_view.append_line(msg)

    # --------------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        try:
            self.port_edit.setText(str(self.settings.value("port", 13666)))
            pm = int(self.settings.value("packet_ms", 7))
            idx = self.packet_combo.findData(pm)
            if idx >= 0:
                self.packet_combo.setCurrentIndex(idx)
            rate = int(self.settings.value("rate", 48000))
            idx = self.rate_combo.findData(rate)
            if idx >= 0:
                self.rate_combo.setCurrentIndex(idx)
            ch = int(self.settings.value("channels", 2))
            idx = self.ch_combo.findData(ch)
            if idx >= 0:
                self.ch_combo.setCurrentIndex(idx)
            size = self.settings.value("window_size")
            if isinstance(size, QSize) and size.width() >= 1000 and size.height() >= 740:
                self.resize(size)
        except Exception:
            pass

    def _save_settings(self) -> None:
        try:
            d = self.device_combo.currentData()
            if isinstance(d, DeviceInfo):
                self.settings.setValue("device_sig", self._device_sig(d))
            self.settings.setValue("port", self.port_edit.text())
            self.settings.setValue("rate", int(self.rate_combo.currentData() or 48000))
            self.settings.setValue("channels", int(self.ch_combo.currentData() or 2))
            self.settings.setValue("packet_ms", int(self.packet_combo.currentData() or 7))
        except Exception:
            pass

    # ----------------------------------------------------------------- window
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            screen = self.screen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(geo.center() - self.rect().center())
        enable_dark_title_bar(int(self.winId()))

    def closeEvent(self, event) -> None:
        if self._tray is not None and not self._quitting:
            self._save_settings()
            self.settings.setValue("window_size", self.size())
            if self.engine.running or self._busy:
                self.hide()
                self._tray.showMessage("AirWave 仍在推流",
                                       "窗口已最小化到托盘，双击托盘图标可恢复。",
                                       QSystemTrayIcon.MessageIcon.Information, 3000)
                event.ignore()
                return
        self._quitting = True
        self._shutdown()
        event.accept()

    def _quit_app(self) -> None:
        self._quitting = True
        self.settings.setValue("window_size", self.size())
        self._shutdown()
        QApplication.quit()

    def _shutdown(self) -> None:
        self._save_settings()
        try:
            if self.engine is not None:
                self.engine.stop()
        except Exception:
            pass
        if self._tray is not None:
            self._tray.hide()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#060C18"))
        grad.setColorAt(0.55, QColor("#050A14"))
        grad.setColorAt(1.0, QColor("#080D1A"))
        p.fillRect(self.rect(), grad)

        for cx, cy, r, color, alpha in (
            (w * 0.08, h * 0.02, w * 0.42, "#1D4ED8", 34),
            (w * 0.92, h * 0.25, w * 0.36, "#7C3AED", 26),
            (w * 0.55, h * 1.05, w * 0.5, "#0EA5E9", 14),
        ):
            rg = QRadialGradient(QPointF(cx, cy), r)
            c1 = QColor(color)
            c1.setAlpha(alpha)
            rg.setColorAt(0.0, c1)
            rg.setColorAt(1.0, QColor(color).darker(300))
            rg.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rg)
            p.drawEllipse(QPointF(cx, cy), r, r)
