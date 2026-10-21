# AirWave iPhone 接收端

SwiftUI + Network.framework（UDP）+ AVAudioEngine，最低 iOS 15。

## 直接安装（无 Mac）

1. 下载 `AirWave-2.0.0-unsigned.ipa`。
2. Windows 上安装 [Sideloadly](https://sideloadly.io/) 和 iTunes（或 Apple Devices）。
3. iPhone 用数据线连接电脑，把 IPA 拖进 Sideloadly，输入免费 Apple ID。
4. 手机上：设置 → 通用 → VPN与设备管理 → 信任你的开发者证书。
5. 打开 AirWave，右上角设置填电脑 IP，端口 `13666`。

免费 Apple ID 签名的 App 7 天后过期，重新用 Sideloadly 签一次即可，App 数据不会丢。

## 自己构建

工程用 XcodeGen 描述，源码在 `Sources/`：

```bash
brew install xcodegen
cd ios
xcodegen generate
open AirWave.xcodeproj
```

用 Xcode 选择真机运行即可。若要打未签名 IPA，直接运行 GitHub Actions 的
`.github/workflows/build-ipa.yml`。

## 关键实现

- `StreamManager.swift`
  - UDP `NWConnection`，每 750 ms 发 `HELLO` 注册；4 秒收不到任何包自动重连（0.8s→5s 退避）。
  - 断线重连后会强制重新 `configure()`，即使 PC 的 `stream_id` 没变。
  - 音频会话 `.playback + .mixWithOthers`，锁屏/后台继续，且不抢其他 App 的声音。
  - 处理来电中断、音频路由变化、媒体服务重置。
- `AudioPipeline.swift`
  - 自适应 jitter buffer：自动档 80 ms 起，遇到欠载/丢包每次 +15 ms（上限 240 ms），稳定后慢慢回落。
  - 始终预排 3–6 个缓冲（lead），4 ms 定时器补充，不再“播完一个才排下一个”。
  - 丢包用上一包淡出隐藏（PLC），恢复时淡入，避免“咔哒”声。
  - 缓冲过多时每 2 秒最多丢一包，防止两端晶振差异导致延迟越积越大。
  - 欠载后只用 4 个包快速恢复预缓冲，不会一卡就静音很久。
- `JitterBuffer.swift`
  - 32 位序号回绕安全的先后比较；乱序缓存、丢包跳过、超量裁剪。

## 目录

```
ios/
├── project.yml                 XcodeGen 工程定义
├── Sources/
│   ├── AirWaveApp.swift
│   ├── ContentView.swift       主界面
│   ├── SettingsView.swift      设置
│   ├── StreamManager.swift     连接 / 心跳 / 重连 / 会话
│   ├── AudioPipeline.swift     引擎 / 缓冲 / 调度 / PLC
│   ├── JitterBuffer.swift      序号缓冲
│   ├── Components.swift        圆钮 / 电平 / 选择器
│   ├── Theme.swift             配色 / 毛玻璃卡片
│   └── Assets.xcassets         新图标
└── README.md
```

## 已知边界

- 上滑杀掉 App 会停止播放（iOS 不允许后台被杀进程继续跑）。
- iOS 低电量模式会限制后台网络，可能增加卡顿；建议连接时关闭。
- 首次连接必须在 App 前台完成，等状态变为“正在播放”后再锁屏。
