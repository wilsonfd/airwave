import SwiftUI

struct EqualizerBars: View {
    let level: CGFloat
    let active: Bool
    var tint: Color = .awMint

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 24.0, paused: !active)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            HStack(alignment: .center, spacing: 5) {
                ForEach(0..<5, id: \.self) { index in
                    let wave = 0.5 + 0.5 * sin(t * 3.1 + Double(index) * 0.9)
                    let height = 10 + (level * 0.72 + CGFloat(wave) * 0.28) * 46
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [tint, tint.opacity(0.55)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .frame(width: 6, height: height)
                }
            }
            .frame(height: 58)
        }
    }
}

private struct SpinningArc: View {
    var tint: Color = .awViolet

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { context in
            let angle = context.date.timeIntervalSinceReferenceDate
                .truncatingRemainder(dividingBy: 1.3) / 1.3 * 360
            Circle()
                .trim(from: 0.02, to: 0.30)
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: [tint.opacity(0.15), tint, Color.awAccent]),
                        center: .center
                    ),
                    style: StrokeStyle(lineWidth: 4, lineCap: .round)
                )
                .rotationEffect(.degrees(angle))
        }
    }
}

struct OrbButton: View {
    let phase: StreamManager.Phase
    let level: CGFloat
    let size: CGFloat
    let action: () -> Void

    @State private var pulse = false

    private var ringColor: Color {
        switch phase {
        case .playing: return .awMint
        case .connecting, .reconnecting: return .awViolet
        case .waiting: return .awAccent
        case .idle: return .awAccent
        }
    }

    private var discColors: [Color] {
        switch phase {
        case .playing: return [Color(hex: 0x123B38), Color(hex: 0x091922)]
        case .connecting, .reconnecting: return [Color(hex: 0x1B1C46), Color(hex: 0x0A0F22)]
        case .waiting: return [Color(hex: 0x122944), Color(hex: 0x0A1220)]
        case .idle: return [Color(hex: 0x17243D), Color(hex: 0x0A111E)]
        }
    }

    private var title: String {
        switch phase {
        case .idle: return "连接"
        case .connecting: return "连接中"
        case .waiting: return "等待音频"
        case .playing: return "播放中"
        case .reconnecting: return "重连中"
        }
    }

    private var subtitle: String {
        switch phase {
        case .idle: return "TAP TO CONNECT"
        case .connecting: return "CONNECTING"
        case .waiting: return "LISTENING"
        case .playing: return "STREAMING"
        case .reconnecting: return "RECONNECTING"
        }
    }

    var body: some View {
        Button(action: action) {
            ZStack {
                // Outer glow.
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [ringColor.opacity(phase == .playing ? 0.34 : 0.20), Color.clear],
                            center: .center,
                            startRadius: size * 0.12,
                            endRadius: size * 0.52
                        )
                    )
                    .frame(width: size * 1.08, height: size * 1.08)
                    .scaleEffect(phase == .playing && pulse ? 1.04 : 1.0)
                    .opacity(phase == .playing && pulse ? 0.85 : 0.6)

                // Halo rings, nudged by the live level.
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .stroke(ringColor.opacity(0.18 - Double(index) * 0.045), lineWidth: 1)
                        .frame(width: size * (0.80 + CGFloat(index) * 0.075),
                               height: size * (0.80 + CGFloat(index) * 0.075))
                        .scaleEffect(phase == .playing ? 1 + level * (0.06 + CGFloat(index) * 0.015) : 1)
                        .opacity(phase == .playing ? 0.9 : 0.45)
                }

                // Slow rotating outer ring.
                Circle()
                    .stroke(
                        AngularGradient(
                            gradient: Gradient(colors: [
                                ringColor.opacity(0.0),
                                ringColor.opacity(0.55),
                                Color.awViolet.opacity(0.55),
                                ringColor.opacity(0.0)
                            ]),
                            center: .center
                        ),
                        lineWidth: 2
                    )
                    .frame(width: size * 0.91, height: size * 0.91)
                    .rotationEffect(.degrees(pulse ? 360 : 0))
                    .animation(.linear(duration: 9).repeatForever(autoreverses: false), value: pulse)
                    .opacity(0.75)

                // Glass disc.
                Circle()
                    .fill(
                        LinearGradient(colors: discColors,
                                       startPoint: .topLeading,
                                       endPoint: .bottomTrailing)
                    )
                    .frame(width: size * 0.70, height: size * 0.70)
                    .overlay(
                        Circle()
                            .stroke(
                                LinearGradient(
                                    colors: [Color.white.opacity(0.28), Color.white.opacity(0.04)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1
                            )
                    )
                    .shadow(color: Color.black.opacity(0.45), radius: 26, x: 0, y: 18)
                    .overlay(
                        Ellipse()
                            .fill(Color.white.opacity(0.10))
                            .frame(width: size * 0.40, height: size * 0.11)
                            .blur(radius: 9)
                            .offset(y: -size * 0.19),
                        alignment: .center
                    )

                VStack(spacing: size * 0.028) {
                    content
                    Text(title)
                        .font(AWFont.rounded(size * 0.075, .semibold))
                        .foregroundColor(.awText)
                    Text(subtitle)
                        .font(AWFont.mono(size * 0.031, .semibold))
                        .foregroundColor(Color.awDim)
                        .tracking(1.4)
                }
            }
            .frame(width: size, height: size)
            .contentShape(Circle())
        }
        .buttonStyle(PlainButtonStyle())
        .onAppear {
            pulse = true
        }
        .onChange(of: phase) { newPhase in
            if newPhase == .playing {
                pulse = false
                withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                    pulse = true
                }
            }
        }
        .accessibilityLabel(Text(title))
        .accessibilityHint(Text(phase == .idle ? "开始连接电脑" : "断开连接"))
    }

    @ViewBuilder
    private var content: some View {
        switch phase {
        case .idle:
            Image(systemName: "power")
                .font(.system(size: size * 0.16, weight: .light))
                .foregroundColor(.awText)
        case .connecting, .reconnecting:
            SpinningArc(tint: ringColor)
                .frame(width: size * 0.16, height: size * 0.16)
                .padding(.vertical, size * 0.015)
        case .waiting:
            Image(systemName: "waveform")
                .font(.system(size: size * 0.14, weight: .medium))
                .foregroundColor(.awAccent)
                .symbolRenderingMode(.hierarchical)
        case .playing:
            EqualizerBars(level: level, active: true, tint: .awMint)
        }
    }
}

struct ModeSelector: View {
    @Binding var selection: LatencyMode

    var body: some View {
        HStack(spacing: 6) {
            ForEach(LatencyMode.allCases) { mode in
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        selection = mode
                    }
                } label: {
                    Text(mode.title)
                        .font(AWFont.rounded(11.5, .semibold))
                        .foregroundColor(selection == mode ? .awBg : .awMuted)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 7)
                        .background(
                            Capsule()
                                .fill(selection == mode ? Color.awText : Color.white.opacity(0.05))
                        )
                }
                .buttonStyle(PlainButtonStyle())
            }
        }
    }
}

struct StatRow: View {
    let icon: String
    let title: String
    let value: String
    var tint: Color = .awText

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(tint)
                .frame(width: 18)
            Text(title)
                .font(AWFont.rounded(12, .regular))
                .foregroundColor(.awMuted)
            Spacer(minLength: 8)
            Text(value)
                .font(AWFont.mono(12, .semibold))
                .foregroundColor(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
    }
}
