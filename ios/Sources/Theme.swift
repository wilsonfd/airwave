import SwiftUI

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: alpha
        )
    }

    static let awBg = Color(hex: 0x050912)
    static let awBg2 = Color(hex: 0x0A1122)
    static let awCard = Color(hex: 0x0B1423)
    static let awText = Color(hex: 0xE9F0FB)
    static let awMuted = Color(hex: 0x8497B5)
    static let awDim = Color(hex: 0x4E607C)
    static let awAccent = Color(hex: 0x6AA9FF)
    static let awViolet = Color(hex: 0xB18CFF)
    static let awMint = Color(hex: 0x5FE3B6)
    static let awAmber = Color(hex: 0xF5BE6B)
    static let awRed = Color(hex: 0xFF7D8C)
}

enum AWFont {
    static func rounded(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }

    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

/// Slowly drifting aurora that shifts with the connection state.
struct AuroraBackground: View {
    let phase: StreamManager.Phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var topColor: Color {
        switch phase {
        case .playing: return Color(hex: 0x0B2C3A)
        case .connecting, .reconnecting: return Color(hex: 0x0B1B3A)
        case .waiting: return Color(hex: 0x0A1E33)
        case .idle: return Color(hex: 0x070C18)
        }
    }

    private var bottomColor: Color {
        switch phase {
        case .playing: return Color(hex: 0x1B1240)
        case .waiting: return Color(hex: 0x121A38)
        case .connecting, .reconnecting: return Color(hex: 0x151338)
        case .idle: return Color(hex: 0x0A0D1A)
        }
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20.0, paused: reduceMotion)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            ZStack {
                LinearGradient(
                    colors: [topColor, Color.awBg, bottomColor],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                Circle()
                    .fill(Color.awAccent.opacity(phase == .playing ? 0.20 : 0.13))
                    .frame(width: 460, height: 460)
                    .blur(radius: 110)
                    .offset(x: -150 + sin(t * 0.12) * 28,
                            y: -300 + cos(t * 0.10) * 22)

                Circle()
                    .fill(Color.awViolet.opacity(phase == .playing ? 0.22 : 0.15))
                    .frame(width: 420, height: 420)
                    .blur(radius: 120)
                    .offset(x: 160 + cos(t * 0.09) * 34,
                            y: 300 + sin(t * 0.11) * 26)

                // A faint vignette keeps the center readable.
                RadialGradient(
                    colors: [Color.clear, Color.black.opacity(0.34)],
                    center: .center,
                    startRadius: 180,
                    endRadius: 520
                )
            }
        }
        .ignoresSafeArea()
        .animation(.easeInOut(duration: 0.8), value: phase)
    }
}

struct GlassCard<Content: View>: View {
    var corner: CGFloat = 24
    let content: Content

    init(corner: CGFloat = 24, @ViewBuilder content: () -> Content) {
        self.corner = corner
        self.content = content()
    }

    var body: some View {
        content
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: corner, style: .continuous)
                    .fill(Color.white.opacity(0.045))
                    .overlay(
                        RoundedRectangle(cornerRadius: corner, style: .continuous)
                            .stroke(
                                LinearGradient(
                                    colors: [Color.white.opacity(0.14), Color.white.opacity(0.03)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1
                            )
                    )
            )
            .shadow(color: Color.black.opacity(0.28), radius: 24, x: 0, y: 14)
    }
}

struct Pill: View {
    let text: String
    var color: Color = .awAccent
    var icon: String? = nil

    var body: some View {
        HStack(spacing: 5) {
            if let icon = icon {
                Image(systemName: icon)
                    .font(.system(size: 9, weight: .bold))
            }
            Text(text)
                .font(AWFont.mono(10.5, .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .foregroundColor(color)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(
            Capsule().fill(color.opacity(0.12))
        )
        .overlay(
            Capsule().stroke(color.opacity(0.24), lineWidth: 1)
        )
    }
}

struct SectionLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(AWFont.mono(10, .semibold))
            .foregroundColor(Color.awDim)
            .tracking(1.2)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct TinyMetric: View {
    let title: String
    let value: String
    var tint: Color = .awText

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(AWFont.rounded(10.5, .medium))
                .foregroundColor(Color.awMuted)
            Text(value)
                .font(AWFont.mono(14, .semibold))
                .foregroundColor(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
