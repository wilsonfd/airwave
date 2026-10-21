import SwiftUI
import UIKit

struct ContentView: View {
    @StateObject private var manager = StreamManager()
    @AppStorage("aw_ip") private var ip = ""
    @AppStorage("aw_port") private var port = "13666"
    @AppStorage("aw_autoreconnect") private var autoReconnect = true
    @State private var showSettings = false
    @State private var showIPHint = false
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        GeometryReader { geo in
            let orbSize = min(min(max(190, geo.size.width * 0.78), geo.size.height * 0.34), 320)

            ZStack(alignment: .topLeading) {
                AuroraBackground(phase: manager.phase)

                VStack(spacing: 0) {
                    header
                    Spacer(minLength: 4)
                    OrbButton(phase: manager.phase,
                              level: CGFloat(manager.level),
                              size: orbSize,
                              action: handleTap)
                    statusBlock
                        .padding(.top, 8)
                    Spacer(minLength: 10)
                    bottomPanel
                }
                .frame(width: max(0, geo.size.width - 40))
                .padding(.top, 4)
                .padding(.bottom, 10)
                .offset(x: 20)
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView(manager: manager,
                         ip: $ip,
                         port: $port,
                         autoReconnect: $autoReconnect)
        }
        .onAppear {
            manager.autoReconnect = autoReconnect
            if ProcessInfo.processInfo.environment["AIRWAVE_UITEST"] == "1" {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                    showSettings = true
                }
            }
        }
        .onChange(of: autoReconnect) { value in
            manager.autoReconnect = value
        }
        .onChange(of: scenePhase) { value in
            manager.handleScenePhase(value)
        }
        .alert(isPresented: $showIPHint) {
            Alert(
                title: Text("先填写电脑 IP"),
                message: Text("打开右上角设置，输入电脑上 AirWave 显示的局域网地址，再点连接。"),
                primaryButton: .default(Text("去设置")) { showSettings = true },
                secondaryButton: .cancel(Text("稍后"))
            )
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 10) {
            Image("Logo")
                .resizable()
                .interpolation(.high)
                .frame(width: 38, height: 38)
                .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
                .shadow(color: Color.awAccent.opacity(0.25), radius: 10, x: 0, y: 5)

            VStack(alignment: .leading, spacing: 1) {
                Text("AirWave")
                    .font(AWFont.rounded(21, .bold))
                    .foregroundColor(.awText)
                Text("局域网无损音频")
                    .font(AWFont.rounded(10.5, .medium))
                    .foregroundColor(.awMuted)
            }

            Spacer()

            Button {
                showSettings = true
            } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.awText)
                    .frame(width: 40, height: 40)
                    .background(
                        Circle()
                            .fill(Color.white.opacity(0.06))
                            .overlay(Circle().stroke(Color.white.opacity(0.12), lineWidth: 1))
                    )
            }
            .buttonStyle(PlainButtonStyle())
            .accessibilityLabel(Text("设置"))
        }
    }

    // MARK: - Status

    private var statusBlock: some View {
        VStack(spacing: 5) {
            Text(phaseTitle)
                .font(AWFont.rounded(25, .bold))
                .foregroundColor(.awText)
                .minimumScaleFactor(0.8)

            Text(manager.statusText)
                .font(AWFont.rounded(12, .regular))
                .foregroundColor(.awMuted)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .padding(.horizontal, 14)

            if manager.phase != .idle {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        if !manager.serverName.isEmpty {
                            Pill(text: manager.serverName, color: .awAccent, icon: "desktopcomputer")
                        }
                        if !manager.formatText.isEmpty {
                            Pill(text: manager.formatText, color: .awViolet)
                        }
                        if manager.phase == .playing {
                            Pill(text: String(format: "%.0f ms", manager.latencyMs), color: .awMint)
                            Pill(text: String(format: "丢包 %.1f%%", manager.lossPercent),
                                 color: manager.lossPercent > 2 ? .awAmber : .awMuted)
                        }
                    }
                    .padding(.horizontal, 4)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 30)
                .clipped()
                .padding(.top, 2)
            } else if !ip.isEmpty {
                Text("\(ip) : \(port)")
                    .font(AWFont.mono(11, .medium))
                    .foregroundColor(.awDim)
                    .padding(.top, 2)
            }
        }
        .animation(.easeInOut(duration: 0.35), value: manager.phase)
    }

    // MARK: - Bottom panel

    private var bottomPanel: some View {
        GlassCard(corner: 22) {
            VStack(spacing: 10) {
                HStack {
                    SectionLabel(text: "延迟模式")
                    Spacer()
                    Text(manager.mode.subtitle)
                        .font(AWFont.rounded(9.5, .regular))
                        .foregroundColor(.awDim)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }

                ModeSelector(selection: Binding(
                    get: { manager.mode },
                    set: { manager.setMode($0) }
                ))

                Rectangle()
                    .fill(Color.white.opacity(0.07))
                    .frame(height: 1)

                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: 12),
                        GridItem(.flexible(), spacing: 12),
                    ],
                    alignment: .leading,
                    spacing: 10
                ) {
                    TinyMetric(title: "缓冲", value: String(format: "%.0f ms", manager.bufferMs),
                               tint: manager.bufferMs > 200 ? .awAmber : .awText)
                    TinyMetric(title: "丢包", value: String(format: "%.1f%%", manager.lossPercent),
                               tint: manager.lossPercent > 2 ? .awAmber : .awText)
                    TinyMetric(title: "重连", value: "\(manager.reconnects)",
                               tint: manager.reconnects > 0 ? .awAmber : .awText)
                    TinyMetric(title: "欠载", value: "\(manager.underruns)",
                               tint: manager.underruns > 0 ? .awAmber : .awText)
                }

                if manager.phase == .idle {
                    Text(ip.isEmpty
                         ? "先在设置里填写电脑 IP；手机与电脑需连接同一个 WiFi。"
                         : "点上方圆钮连接电脑；锁屏/切后台仍会继续播放。")
                        .font(AWFont.rounded(10, .regular))
                        .foregroundColor(.awDim)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity)
                }
            }
        }
    }

    private var phaseTitle: String {
        switch manager.phase {
        case .idle: return "未连接"
        case .connecting: return "正在连接"
        case .waiting: return "已连接"
        case .playing: return "正在播放"
        case .reconnecting: return "正在重连"
        }
    }

    // MARK: - Actions

    private func handleTap() {
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.impactOccurred()

        if manager.phase == .idle {
            let trimmed = ip.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else {
                showIPHint = true
                return
            }
            let value = Int(port) ?? 13666
            manager.connect(host: trimmed, port: value)
        } else {
            manager.disconnect()
        }
    }
}
