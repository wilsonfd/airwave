# AirWave Windows 推流端

Python 3.10+ / PySide6 / PyAudioWPatch（WASAPI loopback）。

## 开发运行

```powershell
python -m pip install -r requirements.txt
python app.py
```

## 打包

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean AirWaveServer.spec
& "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
```

- `dist/AirWaveServer.exe`：单文件，无控制台。
- `dist/installer/AirWaveSetup-2.0.0.exe`：安装包，含防火墙规则。

## 诊断

```powershell
python app.py --diagnose-out diag.txt
# 或打包后
.\dist\AirWaveServer.exe --diagnose-out diag.txt
```

会输出本机 IP、WASAPI 设备列表、默认输出回环，不启动 GUI。

## 关键实现

- `airwave/server.py`
  - 采集回调只做拷贝 + RMS，发送线程独立，避免网卡阻塞音频线程。
  - 队列最多 6 个包，积压超过 2 个就丢旧包，延迟不滚雪球。
  - `SO_EXCLUSIVEADDRUSE` + 系统 UDP 表检查，端口冲突直接报错。
  - `SIO_UDP_CONNRESET=False`，手机断开后的 ICMP 不会打断 `recvfrom`。
  - 客户端 15 秒无 HELLO 才清理；META 每 1.25 秒重发。
- `airwave/protocol.py`：HELLO / BYE / META / AUDIO，字节序与 iOS 端一致。
- `airwave/widgets.py`：自绘电源按钮、实时电平、状态胶囊、客户端列表。
- `airwave/winutil.py`：防火墙、深色标题栏、任务栏 AppUserModelID、端口检测。

## 已知边界

- 只抓 WASAPI 共享模式；独占模式/受保护音频可能抓不到，用 VB-Cable 兜底。
- 设备采样率必须被驱动支持；不支持时自动回退到设备原生格式并在日志提示。
- 仅 IPv4 局域网，不做加密和公网穿透。
