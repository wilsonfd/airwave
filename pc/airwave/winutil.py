# -*- coding: utf-8 -*-
"""Small Windows helpers (all failures are non-fatal)."""
from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

CREATE_NO_WINDOW = 0x08000000


def set_app_user_model_id(app_id: str = "AirWave.Server.2") -> None:
    """Make the taskbar show our icon instead of the generic Python one."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def enable_dark_title_bar(hwnd: int) -> None:
    if sys.platform != "win32":
        return
    try:
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE on Windows 10 2004+/11.
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_uint(20),
            ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def time_period(enable: bool) -> None:
    """1 ms timer resolution: keeps UDP pacing and sleep() precise."""
    if sys.platform != "win32":
        return
    try:
        fn = ctypes.windll.winmm.timeBeginPeriod if enable else ctypes.windll.winmm.timeEndPeriod
        fn(1)
    except Exception:
        pass


def add_firewall_rule(port: int) -> bool:
    """Ask for UAC once and create an inbound UDP allow rule."""
    if sys.platform != "win32":
        return False
    rule = f"AirWave_UDP_{port}"
    params = (f'advfirewall firewall add rule name={rule} dir=in '
              f'action=allow protocol=UDP localport={port} profile=any')
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "netsh.exe", params, None, 0)
        return int(rc) > 32
    except Exception:
        return False


def firewall_rule_exists(port: int) -> bool:
    if sys.platform != "win32":
        return False
    rule = f"AirWave_UDP_{port}"
    try:
        proc = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW, timeout=6)
        out = proc.stdout.decode("mbcs", errors="ignore")
        return proc.returncode == 0 and ("AirWave" in out or "UDP" in out)
    except Exception:
        return False


def udp_port_in_use(port: int) -> bool:
    """True when any IPv4 UDP socket already owns this local port.

    SO_REUSEADDR is commonly set by older Python/PortAudio apps, and Windows
    will happily let a second process bind the same UDP port while stealing
    datagrams from it.  Checking the system table gives the user a clear error
    instead of a mysterious "connected but no audio".
    """
    if sys.platform != "win32":
        return False
    try:
        AF_INET = 2
        UDP_TABLE_OWNER_PID = 1
        iphlpapi = ctypes.windll.iphlpapi
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), False,
                                     AF_INET, UDP_TABLE_OWNER_PID, 0)
        if size.value <= 4:
            return False
        buf = ctypes.create_string_buffer(size.value)
        rc = iphlpapi.GetExtendedUdpTable(buf, ctypes.byref(size), False,
                                          AF_INET, UDP_TABLE_OWNER_PID, 0)
        if rc != 0:
            return False
        num = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
        for i in range(int(num)):
            offset = 4 + i * 12
            raw = ctypes.cast(ctypes.addressof(buf) + offset + 4,
                              ctypes.POINTER(wintypes.DWORD))[0]
            # dwLocalPort is stored in network byte order in the low 16 bits.
            local_port = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
            if local_port == port:
                return True
    except Exception:
        return False
    return False
