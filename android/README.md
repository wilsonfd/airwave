# AirWave Android 接收端

Kotlin + 原生 Android View，无第三方 UI 依赖；`AudioTrack` 低延迟流式播放。

## 构建

需要 JDK 17、Android SDK 34、Gradle 8.7：

```bash
cd android
gradle assembleDebug
```

或在 GitHub Actions 手动运行 **Build Android APK**，下载 `AirWave-android` artifact。

输出：

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Debug 签名，可直接 Sideload 安装；首次安装需允许“安装未知应用”。

## 关键实现

- `UdpClient.kt`：UDP 13666、HELLO 750ms、META/AUDIO 解析、断线重连。
- `AudioEngine.kt`：`AudioTrack` + 序号 jitter buffer；7ms 包、低延迟模式；时钟漂移裁剪不计丢包；丢包用上一包淡出掩盖。
- `AirwaveCore.kt`：进程级状态、WiFi 高性能锁、WakeLock、AudioFocus。
- `StreamService.kt`：前台服务，锁屏/切后台继续播放。
- `MainActivity.kt` / `SettingsActivity.kt`：暗色玻璃 UI、圆钮、5 档延迟、统计、保存 IP。
- 版本：2.2.0 build 7（`versionName` / `versionCode`）。
