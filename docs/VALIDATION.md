# AirWave 2.0 验证记录

测试环境：Windows 10/11 x64，Realtek + VB-Cable，48 kHz / 立体声；Python 3.13；iPhone 端由 GitHub Actions macOS runner 编译。

## Windows 端

| 项目 | 方法 | 结果 |
|---|---|---|
| 设备枚举 | `--diagnose-out`，WASAPI loopback + CABLE Output | 找到 7 个设备，默认扬声器回环正确 |
| UDP 包格式 | 假手机发 `HELLO`，解析 META / AUDIO | `packet_frames=336`，`packet_ms=7.0`，单包 1349 B（含头） |
| 16 秒连续接收 | `pc/tests/soak.py` | 2286 包，序号断档 0，服务端 dropped 0，send_errors 0 |
| 包间隔 | 同上 | 平均 7.00 ms，p95 12.96 ms，最大 23.76 ms（接收端 Python 调度抖动） |
| 5 ms / 7 ms 模式 | `pc/tests/smoke_server.py 5/7` | 960 B / 1344 B 负载，均在 MTU 内 |
| 客户端重连 | BYE 后重新 HELLO | 无需重启推流，立即恢复 META + 音频 |
| 端口冲突 | 两个服务端绑定 13666 | 第二个明确报“端口已被占用”，不会抢包 |
| 打包 exe | `--diagnose-out` + `--smoke-test` | 均通过，窗口正常渲染 |
| 单实例 | 启动两次 exe | 第二实例退出；PyInstaller onefile 会显示父子两个进程属正常 |
| 安装包 | 静默安装 / 卸载 | 文件、图标、README、卸载项正常 |
| 防火墙 | 安装时添加 / 卸载时删除 | 规则 `AirWave_UDP_13666` 正确创建和清理 |
| 实时电平 | 播放 440 Hz 测试音 | UI 电平 79%，波形正常 |

## iPhone 端

| 项目 | 方法 | 结果 |
|---|---|---|
| 编译 | GitHub Actions `Build unsigned IPA`（Xcode 16.2） | 成功，无编译警告 |
| IPA 结构 | 解包检查 | `Payload/AirWave.app/AirWave`、Assets.car、Info.plist 完整 |
| Info.plist | plistlib 检查 | bundle id、iOS 15、`UIBackgroundModes=audio`、本地网络说明正确 |
| 图标 | 1024/各尺寸检查 | 全部 RGB 无 alpha，尺寸正确 |
| 运行 | 需要在真机侧载后验证 | 本次未连接实体 iPhone，无法替代真机听感测试 |

> iOS 的抖动缓冲、PLC、重连逻辑由代码审查和编译验证；真机上的实际延迟/卡顿仍需用 Sideloadly 安装后试听确认。
