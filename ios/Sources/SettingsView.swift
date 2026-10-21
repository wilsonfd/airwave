import SwiftUI
import UIKit

struct SettingsView: View {
    @ObservedObject var manager: StreamManager
    @Binding var ip: String
    @Binding var port: String
    @Binding var autoReconnect: Bool

    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Field?

    @State private var draftIP = ""
    @State private var draftPort = ""
    @State private var validationMessage: String? = nil
    @State private var saved: [SavedEndpoint] = []
    @State private var savedFlash = false

    private enum Field: Hashable {
        case ip
        case port
    }

    var body: some View {
        NavigationView {
            ZStack {
                AuroraBackground(phase: manager.phase)
                    .ignoresSafeArea()

                GeometryReader { geo in
                    ScrollView {
                        VStack(spacing: 14) {
                            connectionCard
                            savedCard
                            latencyCard
                            playbackCard
                            statsCard
                            helpCard
                            applyButton
                        }
                        .frame(width: max(0, geo.size.width - 36))
                        .padding(.horizontal, 18)
                        .padding(.top, 12)
                        .padding(.bottom, 28)
                        .frame(maxWidth: .infinity)
                    }
                    .onTapGesture { focused = nil }
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("取消") { dismiss() }
                        .foregroundColor(.awMuted)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { applyAndClose() }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.awAccent)
                }
            }
        }
        .navigationViewStyle(StackNavigationViewStyle())
        .onAppear {
            draftIP = ip
            draftPort = port
            saved = SavedEndpointsStore.load()
            if saved.isEmpty,
               ProcessInfo.processInfo.environment["AIRWAVE_UITEST"] == "1" {
                saved = [
                    SavedEndpoint(host: "192.168.1.30", port: 13666, lastUsed: Date()),
                    SavedEndpoint(host: "192.168.1.88", port: 13666,
                                  lastUsed: Date().addingTimeInterval(-7200)),
                ]
                SavedEndpointsStore.save(saved)
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Cards

    private var connectionCard: some View {
        GlassCard(corner: 22) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    SectionLabel(text: "电脑连接")
                    Spacer()
                    Pill(text: phaseText, color: phaseColor)
                }

                fieldRow(icon: "network", placeholder: "电脑 IP，例如 192.168.1.10", text: $draftIP, field: .ip)
                fieldRow(icon: "antenna.radiowaves.left.and.right", placeholder: "端口", text: $draftPort, field: .port)

                if let message = validationMessage {
                    Text(message)
                        .font(AWFont.rounded(10.5, .medium))
                        .foregroundColor(.awRed)
                } else {
                    Text("电脑上打开 AirWave 后，右上角会显示本机 IP 和端口 13666。")
                        .font(AWFont.rounded(10, .regular))
                        .foregroundColor(.awDim)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 8) {
                    Button {
                        saveDraft()
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: savedFlash ? "checkmark.circle.fill" : "square.and.arrow.down")
                                .font(.system(size: 11, weight: .semibold))
                            Text(savedFlash ? "已保存" : "保存此地址")
                                .font(AWFont.rounded(11, .semibold))
                        }
                        .foregroundColor(savedFlash ? .awMint : .awAccent)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
                        .background(
                            Capsule().fill((savedFlash ? Color.awMint : Color.awAccent).opacity(0.12))
                        )
                        .overlay(
                            Capsule().stroke(
                                (savedFlash ? Color.awMint : Color.awAccent).opacity(0.28),
                                lineWidth: 1
                            )
                        )
                    }
                    .buttonStyle(PlainButtonStyle())

                    Spacer()

                    Text(saved.isEmpty ? "未保存" : "已保存 \(saved.count) 个")
                        .font(AWFont.rounded(9.5, .regular))
                        .foregroundColor(.awDim)
                }
            }
        }
    }

    private var savedCard: some View {
        GlassCard(corner: 22) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    SectionLabel(text: "已保存的电脑")
                    Spacer()
                    if !saved.isEmpty {
                        Text("点击填入")
                            .font(AWFont.rounded(9.5, .regular))
                            .foregroundColor(.awDim)
                    }
                }

                if saved.isEmpty {
                    HStack(spacing: 8) {
                        Image(systemName: "bookmark")
                            .font(.system(size: 12))
                            .foregroundColor(.awDim)
                        Text("在上方填写 IP 和端口，点“保存此地址”，以后就不用再输入了。")
                            .font(AWFont.rounded(10.5, .regular))
                            .foregroundColor(.awDim)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.vertical, 4)
                } else {
                    ForEach(Array(saved.enumerated()), id: \.element.id) { index, item in
                        HStack(spacing: 8) {
                            Button {
                                draftIP = item.host
                                draftPort = "\(item.port)"
                                validationMessage = nil
                                savedFlash = false
                                focused = nil
                            } label: {
                                HStack(spacing: 10) {
                                    Image(systemName: "desktopcomputer")
                                        .font(.system(size: 12, weight: .medium))
                                        .foregroundColor(.awAccent)
                                        .frame(width: 18)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.host)
                                            .font(AWFont.mono(12.5, .semibold))
                                            .foregroundColor(.awText)
                                            .lineLimit(1)
                                            .truncationMode(.middle)
                                        Text("端口 " + String(item.port) + " · " + lastUsedText(item.lastUsed))
                                            .font(AWFont.rounded(9.5, .regular))
                                            .foregroundColor(.awDim)
                                            .lineLimit(1)
                                            .minimumScaleFactor(0.8)
                                    }
                                    Spacer(minLength: 4)
                                    if isDraft(item) {
                                        Image(systemName: "checkmark.circle.fill")
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundColor(.awMint)
                                    }
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(PlainButtonStyle())

                            Button {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    saved = SavedEndpointsStore.remove(id: item.id, from: saved)
                                    SavedEndpointsStore.save(saved)
                                }
                            } label: {
                                Image(systemName: "trash")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.awDim)
                                    .frame(width: 30, height: 30)
                            }
                            .buttonStyle(PlainButtonStyle())
                        }
                        .padding(.vertical, 5)

                        if index < saved.count - 1 {
                            Rectangle()
                                .fill(Color.white.opacity(0.06))
                                .frame(height: 1)
                        }
                    }

                    Text("最多保存 \(SavedEndpointsStore.maxCount) 个地址；点右侧垃圾桶可删除。")
                        .font(AWFont.rounded(9.5, .regular))
                        .foregroundColor(.awDim)
                        .padding(.top, 2)
                }
            }
        }
    }

    private var latencyCard: some View {
        GlassCard(corner: 22) {
            VStack(alignment: .leading, spacing: 10) {
                SectionLabel(text: "延迟模式")
                ForEach(LatencyMode.allCases) { mode in
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            manager.setMode(mode)
                        }
                    } label: {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(mode.title)
                                    .font(AWFont.rounded(13.5, .semibold))
                                    .foregroundColor(.awText)
                                Text(mode.detail)
                                    .font(AWFont.rounded(10, .regular))
                                    .foregroundColor(.awDim)
                                    .multilineTextAlignment(.leading)
                            }
                            Spacer()
                            Image(systemName: manager.mode == mode ? "checkmark.circle.fill" : "circle")
                                .font(.system(size: 18, weight: .medium))
                                .foregroundColor(manager.mode == mode ? .awMint : .awDim)
                        }
                        .padding(.vertical, 8)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(PlainButtonStyle())

                    if mode != LatencyMode.allCases.last {
                        Rectangle()
                            .fill(Color.white.opacity(0.06))
                            .frame(height: 1)
                    }
                }
            }
        }
    }

    private var playbackCard: some View {
        GlassCard(corner: 22) {
            VStack(alignment: .leading, spacing: 12) {
                SectionLabel(text: "播放")
                Toggle(isOn: $autoReconnect) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("断线自动重连")
                            .font(AWFont.rounded(13, .medium))
                            .foregroundColor(.awText)
                        Text("电脑重启或 WiFi 抖动后自动恢复")
                            .font(AWFont.rounded(10, .regular))
                            .foregroundColor(.awDim)
                    }
                }
                .toggleStyle(SwitchToggleStyle(tint: .awAccent))

                Rectangle()
                    .fill(Color.white.opacity(0.06))
                    .frame(height: 1)

                HStack(spacing: 8) {
                    Image(systemName: "moon.stars")
                        .font(.system(size: 12))
                        .foregroundColor(.awViolet)
                    Text("锁屏/切后台继续播放；与其他 App 声音混音共存。")
                        .font(AWFont.rounded(10.5, .regular))
                        .foregroundColor(.awMuted)
                }
            }
        }
    }

    private var statsCard: some View {
        GlassCard(corner: 22) {
            VStack(alignment: .leading, spacing: 10) {
                SectionLabel(text: "实时状态")
                StatRow(icon: "waveform.path.ecg", title: "缓冲", value: String(format: "%.0f ms", manager.bufferMs))
                StatRow(icon: "timer", title: "预估延迟", value: String(format: "%.0f ms", manager.latencyMs), tint: .awMint)
                StatRow(icon: "arrow.down.right.and.arrow.up.left", title: "丢包",
                        value: String(format: "%.1f%%", manager.lossPercent),
                        tint: manager.lossPercent > 2 ? .awAmber : .awText)
                StatRow(icon: "exclamationmark.triangle", title: "欠载次数", value: "\(manager.underruns)",
                        tint: manager.underruns > 0 ? .awAmber : .awText)
                StatRow(icon: "arrow.clockwise", title: "重连次数", value: "\(manager.reconnects)")
                StatRow(icon: "square.stack.3d.up", title: "已收音频包", value: "\(manager.receivedPackets)")
            }
        }
    }

    private var helpCard: some View {
        GlassCard(corner: 22) {
            VStack(alignment: .leading, spacing: 9) {
                SectionLabel(text: "使用说明")
                helpRow("wifi", "手机和电脑连接同一个 WiFi，优先 5 GHz。")
                helpRow("lock.shield", "首次连接如弹出“本地网络”权限，请选择允许。")
                helpRow("speaker.wave.2", "电脑端先点“开始推流”，手机再点连接。")
                helpRow("bolt.slash", "声音卡顿时把延迟模式切到“平衡”或“稳定”。")
                helpRow("xmark.circle", "上滑彻底关闭 App 才会停止播放。")

                Button {
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "gearshape")
                        Text("打开系统设置")
                    }
                    .font(AWFont.rounded(11, .semibold))
                    .foregroundColor(.awAccent)
                    .padding(.top, 4)
                }
                .buttonStyle(PlainButtonStyle())
            }
        }
    }

    private var applyButton: some View {
        Button {
            applyAndClose()
        } label: {
            Text("保存并使用")
                .font(AWFont.rounded(15, .semibold))
                .foregroundColor(.awBg)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    LinearGradient(
                        colors: [Color.awMint, Color.awAccent],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .shadow(color: Color.awAccent.opacity(0.25), radius: 16, x: 0, y: 8)
        }
        .buttonStyle(PlainButtonStyle())
    }

    // MARK: - Helpers

    private func fieldRow(icon: String, placeholder: String, text: Binding<String>, field: Field) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.awAccent)
                .frame(width: 18)
            TextField(placeholder, text: text)
                .font(AWFont.mono(13, .medium))
                .foregroundColor(.awText)
                .keyboardType(field == .port ? .numberPad : .numbersAndPunctuation)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
                .focused($focused, equals: field)
                .submitLabel(field == .port ? .done : .next)
                .onSubmit {
                    focused = field == .ip ? .port : nil
                }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 11)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.white.opacity(0.055))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(focused == field ? Color.awAccent.opacity(0.65) : Color.white.opacity(0.08),
                        lineWidth: 1)
        )
    }

    private func helpRow(_ icon: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.awMuted)
                .frame(width: 16)
                .padding(.top, 1)
            Text(text)
                .font(AWFont.rounded(10.5, .regular))
                .foregroundColor(.awMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var phaseText: String {
        switch manager.phase {
        case .idle: return "未连接"
        case .connecting: return "连接中"
        case .waiting: return "已连接"
        case .playing: return "播放中"
        case .reconnecting: return "重连中"
        }
    }

    private var phaseColor: Color {
        switch manager.phase {
        case .playing: return .awMint
        case .waiting: return .awAccent
        case .connecting, .reconnecting: return .awViolet
        case .idle: return .awMuted
        }
    }

    private static let relativeFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        formatter.locale = Locale(identifier: "zh_CN")
        return formatter
    }()

    private func lastUsedText(_ date: Date) -> String {
        Self.relativeFormatter.localizedString(for: date, relativeTo: Date())
    }

    private func isDraft(_ item: SavedEndpoint) -> Bool {
        guard let value = Int(draftPort) else { return false }
        return item.host.caseInsensitiveCompare(draftIP.trimmingCharacters(in: .whitespaces)) == .orderedSame
            && item.port == value
    }

    private func saveDraft() {
        let trimmedIP = draftIP.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedPort = draftPort.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedIP.isEmpty else {
            validationMessage = "请填写电脑的局域网 IP"
            focused = .ip
            return
        }
        guard let value = Int(trimmedPort), value >= 1024, value <= 65535 else {
            validationMessage = "端口需在 1024–65535 之间"
            focused = .port
            return
        }

        validationMessage = nil
        saved = SavedEndpointsStore.add(host: trimmedIP, port: value, to: saved)
        SavedEndpointsStore.save(saved)
        focused = nil
        withAnimation(.easeInOut(duration: 0.2)) {
            savedFlash = true
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            withAnimation(.easeInOut(duration: 0.2)) {
                savedFlash = false
            }
        }
    }

    private func applyAndClose() {
        let trimmedIP = draftIP.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedPort = draftPort.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedIP.isEmpty else {
            validationMessage = "请填写电脑的局域网 IP"
            focused = .ip
            return
        }
        guard let value = Int(trimmedPort), value >= 1024, value <= 65535 else {
            validationMessage = "端口需在 1024–65535 之间"
            focused = .port
            return
        }

        validationMessage = nil
        ip = trimmedIP
        port = String(value)
        saved = SavedEndpointsStore.add(host: trimmedIP, port: value, to: saved)
        SavedEndpointsStore.save(saved)
        manager.autoReconnect = autoReconnect
        dismiss()
    }
}
