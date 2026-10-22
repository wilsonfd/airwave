import AVFoundation
import Foundation
import Network
import SwiftUI

enum LatencyMode: String, CaseIterable, Identifiable {
    case auto
    case low
    case ultra
    case balanced
    case stable

    var id: String { rawValue }

    var title: String {
        switch self {
        case .auto: return "自动"
        case .low: return "低延迟"
        case .ultra: return "极低延迟"
        case .balanced: return "平衡"
        case .stable: return "稳定"
        }
    }

    var subtitle: String {
        switch self {
        case .auto: return "自动调节"
        case .low: return "约 85 ms"
        case .ultra: return "约 50–70 ms"
        case .balanced: return "约 220 ms"
        case .stable: return "约 380 ms"
        }
    }

    var detail: String {
        switch self {
        case .auto: return "按网络抖动自动调整，推荐"
        case .low: return "约 75–100 ms，适合同一房间"
        case .ultra: return "实验档：PC 选 3ms，5GHz 近距离；抖动大时会断音"
        case .balanced: return "约 190–240 ms，日常使用"
        case .stable: return "约 350–410 ms，隔墙/弱网更稳"
        }
    }

    var pipelineMode: AudioPipeline.Mode {
        switch self {
        case .auto: return .auto
        case .low: return .low
        case .ultra: return .ultra
        case .balanced: return .balanced
        case .stable: return .stable
        }
    }
}

private struct StreamMeta: Decodable {
    let rate: Double
    let channels: Int
    let packetFrames: Int
    let packetMs: Double
    let streamID: String
    let name: String?

    enum CodingKeys: String, CodingKey {
        case rate
        case channels
        case packetFrames = "packet_frames"
        case packetMs = "packet_ms"
        case streamID = "stream_id"
        case name
    }
}

final class StreamManager: ObservableObject {
    enum Phase: Equatable {
        case idle
        case connecting
        case waiting
        case playing
        case reconnecting
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var statusText = "点上方圆钮开始连接"
    @Published private(set) var serverName = ""
    @Published private(set) var formatText = ""
    @Published private(set) var isConnected = false
    @Published private(set) var level: Float = 0

    @Published private(set) var bufferMs: Double = 0
    @Published private(set) var latencyMs: Double = 0
    @Published private(set) var lossPercent: Double = 0
    @Published private(set) var underruns: Int = 0
    @Published private(set) var reconnects: Int = 0
    @Published private(set) var receivedPackets: Int = 0

    @Published var mode: LatencyMode {
        didSet {
            pipeline.setMode(mode.pipelineMode)
            UserDefaults.standard.set(mode.rawValue, forKey: "aw_mode")
        }
    }

    var autoReconnect = true

    private let netQueue = DispatchQueue(label: "com.wilsonfd.airwave.network")
    private var connection: NWConnection?
    private var helloSource: DispatchSourceTimer?
    private var watchdog: DispatchSourceTimer?

    private var host = ""
    private var port: UInt16 = 13666
    private var wantConnected = false
    private var reconnectScheduled = false
    private var reconnectAttempt = 0

    private var lastPacketAt = Date()
    private var lastAudioAt = Date()
    private var currentStreamID = ""
    private var currentRate: Double = 0
    private var currentChannels: Int = 0
    private var currentPacketFrames: Int = 0
    private var currentPacketMs: Double = 0

    private let pipeline = AudioPipeline()
    private var observers: [NSObjectProtocol] = []

    init() {
        let saved = UserDefaults.standard.string(forKey: "aw_mode") ?? LatencyMode.auto.rawValue
        mode = LatencyMode(rawValue: saved) ?? .auto

        pipeline.onLevel = { [weak self] value in
            self?.level = value
        }
        pipeline.onStarted = { [weak self] in
            guard let self = self else { return }
            DispatchQueue.main.async {
                guard self.wantConnected else { return }
                self.phase = .playing
                self.statusText = "正在播放"
                self.isConnected = true
                self.reconnectAttempt = 0
            }
        }
        pipeline.onStats = { [weak self] stats in
            guard let self = self else { return }
            DispatchQueue.main.async {
                self.bufferMs = stats.bufferMs
                self.latencyMs = stats.latencyMs
                self.lossPercent = stats.lossPercent
                self.underruns = stats.underruns
                self.receivedPackets = stats.received
            }
        }
        pipeline.onError = { [weak self] message in
            guard let self = self else { return }
            DispatchQueue.main.async {
                self.statusText = message
            }
        }

        installObservers()
    }

    deinit {
        for token in observers {
            NotificationCenter.default.removeObserver(token)
        }
        helloSource?.cancel()
        watchdog?.cancel()
        connection?.cancel()
        pipeline.stop()
    }

    // MARK: - User actions

    func connect(host: String, port: Int) {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, port >= 1024, port <= 65535,
              let nwPort = NWEndpoint.Port(rawValue: UInt16(port)) else {
            DispatchQueue.main.async {
                self.phase = .idle
                self.statusText = "请填写正确的电脑 IP 和端口（1024–65535）"
            }
            return
        }

        self.host = trimmed
        self.port = nwPort.rawValue
        wantConnected = true
        reconnectAttempt = 0
        reconnectScheduled = false
        activateAudioSession()

        DispatchQueue.main.async {
            self.phase = .connecting
            self.statusText = "正在连接 \(trimmed):\(nwPort.rawValue)…"
            self.isConnected = false
            self.serverName = ""
            self.formatText = ""
            self.level = 0
            self.bufferMs = 0
            self.latencyMs = 0
            self.lossPercent = 0
            self.underruns = 0
            self.receivedPackets = 0
            self.reconnects = 0
        }

        netQueue.async { [weak self] in
            self?.openConnectionLocked()
        }
    }

    func disconnect() {
        wantConnected = false
        reconnectScheduled = false
        netQueue.async { [weak self] in
            guard let self = self else { return }
            self.closeConnectionLocked(stopPipeline: true)
        }
        deactivateAudioSession()
        DispatchQueue.main.async {
            self.phase = .idle
            self.statusText = "点上方圆钮重新连接"
            self.isConnected = false
            self.level = 0
            self.bufferMs = 0
            self.latencyMs = 0
            self.lossPercent = 0
            self.reconnects = 0
        }
    }

    func setMode(_ newMode: LatencyMode) {
        if mode != newMode {
            mode = newMode
        }
    }

    func handleScenePhase(_ scenePhase: ScenePhase) {
        if scenePhase == .active, wantConnected {
            netQueue.async { [weak self] in
                guard let self = self, self.wantConnected,
                      self.connection == nil, !self.reconnectScheduled else { return }
                self.openConnectionLocked()
            }
        }
    }

    // MARK: - Connection

    private func openConnectionLocked() {
        closeConnectionLocked(stopPipeline: true)
        guard wantConnected, !host.isEmpty else { return }

        let params = NWParameters.udp
        params.allowLocalEndpointReuse = true
        params.includePeerToPeer = false
        guard let endpointPort = NWEndpoint.Port(rawValue: port) else { return }

        // Force the next META to rebuild the audio pipeline.  Without this a
        // reconnect to the same PC stream (same stream_id) would skip
        // configure() while the old pipeline is already stopped.
        currentStreamID = ""

        let conn = NWConnection(host: NWEndpoint.Host(host), port: endpointPort, using: params)
        connection = conn
        reconnectScheduled = false

        conn.stateUpdateHandler = { [weak self, weak conn] state in
            guard let self = self, let conn = conn, self.connection === conn else { return }
            switch state {
            case .ready:
                self.handleReadyLocked(conn)
            case .failed(let error):
                self.handleFailureLocked("连接失败：\(error.localizedDescription)")
            case .cancelled:
                if self.wantConnected {
                    self.handleFailureLocked("连接已断开")
                }
            case .waiting(let error):
                DispatchQueue.main.async {
                    guard self.wantConnected else { return }
                    self.statusText = "等待网络：\(error.localizedDescription)"
                }
            default:
                break
            }
        }
        conn.start(queue: netQueue)
    }

    private func handleReadyLocked(_ conn: NWConnection) {
        lastPacketAt = Date()
        lastAudioAt = Date()
        startHelloLocked()
        startWatchdogLocked()
        receiveLoopLocked(conn)
        sendHelloLocked()

        DispatchQueue.main.async {
            guard self.wantConnected else { return }
            self.isConnected = true
            self.phase = .waiting
            self.statusText = "已连接，等待电脑发送音频…"
        }
    }

    private func startHelloLocked() {
        helloSource?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: netQueue)
        timer.schedule(deadline: .now(), repeating: .milliseconds(750), leeway: .milliseconds(80))
        timer.setEventHandler { [weak self] in
            self?.sendHelloLocked()
        }
        timer.resume()
        helloSource = timer
    }

    private func sendHelloLocked() {
        guard wantConnected, let conn = connection else { return }
        conn.send(content: Data("HELLO".utf8),
                  completion: .contentProcessed { _ in })
    }

    private func receiveLoopLocked(_ conn: NWConnection) {
        conn.receiveMessage { [weak self, weak conn] data, _, _, error in
            guard let self = self, let conn = conn, self.connection === conn else { return }
            if let error = error {
                if self.wantConnected {
                    self.handleFailureLocked("接收失败：\(error.localizedDescription)")
                }
                return
            }
            if let data = data, !data.isEmpty {
                self.handlePacketLocked(data)
            }
            if self.connection === conn, self.wantConnected {
                self.receiveLoopLocked(conn)
            }
        }
    }

    private func handlePacketLocked(_ data: Data) {
        let now = Date()
        lastPacketAt = now

        guard let tag = data.first else { return }
        if tag == 0x01 {
            guard data.count >= 3 else { return }
            let length = Int(data[data.startIndex + 1]) << 8 | Int(data[data.startIndex + 2])
            guard data.count >= 3 + length else { return }
            let json = data.subdata(in: 3..<(3 + length))
            guard let meta = try? JSONDecoder().decode(StreamMeta.self, from: json) else { return }
            applyMetaLocked(meta)
        } else if tag == 0x02 {
            guard data.count >= 6 else { return }
            let seq = data.subdata(in: 1..<5).withUnsafeBytes {
                $0.load(as: UInt32.self).bigEndian
            }
            let pcm = data.subdata(in: 5..<data.count)
            lastAudioAt = now
            pipeline.ingest(seq: seq, pcm: pcm)
        }
    }

    private func applyMetaLocked(_ meta: StreamMeta) {
        let changed = meta.streamID != currentStreamID ||
            meta.rate != currentRate ||
            meta.channels != currentChannels ||
            meta.packetFrames != currentPacketFrames ||
            abs(meta.packetMs - currentPacketMs) > 0.01

        currentStreamID = meta.streamID
        currentRate = meta.rate
        currentChannels = meta.channels
        currentPacketFrames = meta.packetFrames
        currentPacketMs = meta.packetMs

        DispatchQueue.main.async {
            guard self.wantConnected else { return }
            self.serverName = meta.name?.isEmpty == false ? meta.name! : "电脑"
            self.formatText = "\(Int(meta.rate)) Hz · \(meta.channels >= 2 ? "立体声" : "单声道") · \(String(format: "%.1f", meta.packetMs)) ms"
            self.reconnectAttempt = 0
            if !self.isConnected {
                self.isConnected = true
            }
            if self.phase == .connecting || self.phase == .reconnecting {
                self.phase = .waiting
                self.statusText = "已连接，等待音频…"
            }
        }

        if changed {
            pipeline.configure(
                sampleRate: meta.rate,
                channels: meta.channels,
                packetFrames: meta.packetFrames,
                packetMs: meta.packetMs,
                streamID: meta.streamID,
                mode: mode.pipelineMode
            )
        }
    }

    private func startWatchdogLocked() {
        watchdog?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: netQueue)
        timer.schedule(deadline: .now() + 1, repeating: .seconds(1), leeway: .milliseconds(150))
        timer.setEventHandler { [weak self] in
            self?.watchdogTickLocked()
        }
        timer.resume()
        watchdog = timer
    }

    private func watchdogTickLocked() {
        guard wantConnected, connection != nil else { return }
        let now = Date()
        // Do not tear down and reconnect just because packets paused.  While
        // locked/backgrounded iOS may coalesce network wake-ups; reconnecting
        // would reset the jitter buffer and turn a short pause into a stutter
        // loop.  Just ask the PC for metadata and show a waiting state.
        if now.timeIntervalSince(lastPacketAt) > 8.0 {
            sendHelloLocked()
            DispatchQueue.main.async {
                guard self.wantConnected, self.phase != .reconnecting else { return }
                if self.phase == .playing {
                    self.phase = .waiting
                    self.statusText = "电脑暂时没有响应，点圆钮可重连"
                }
            }
        } else if now.timeIntervalSince(lastAudioAt) > 2.5 {
            DispatchQueue.main.async {
                guard self.wantConnected, self.phase == .playing else { return }
                self.phase = .waiting
                self.statusText = "电脑暂时没有播放声音"
            }
        }
    }

    private func handleFailureLocked(_ reason: String) {
        guard wantConnected, !reconnectScheduled else { return }
        closeConnectionLocked(stopPipeline: true)

        if !autoReconnect {
            wantConnected = false
            DispatchQueue.main.async {
                self.phase = .idle
                self.statusText = "\(reason)，已停止"
                self.isConnected = false
                self.level = 0
            }
            return
        }

        reconnectAttempt += 1
        let delay = min(5.0, 0.8 * pow(2.0, Double(max(0, reconnectAttempt - 1))))
        reconnectScheduled = true

        DispatchQueue.main.async {
            self.reconnects += 1
            self.phase = .reconnecting
            self.statusText = "\(reason)，\(String(format: "%.0f", delay)) 秒后重连…"
            self.isConnected = false
            self.level = 0
        }

        netQueue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self = self, self.wantConnected, self.reconnectScheduled else { return }
            self.reconnectScheduled = false
            self.openConnectionLocked()
        }
    }

    private func closeConnectionLocked(stopPipeline: Bool) {
        helloSource?.cancel()
        helloSource = nil
        watchdog?.cancel()
        watchdog = nil
        let old = connection
        connection = nil
        old?.cancel()
        if stopPipeline {
            pipeline.stop()
        }
    }

    // MARK: - Audio session

    private func activateAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
            // 10 ms was the stable value. 5 ms made the render callback much
            // more sensitive to scheduling jitter and was the main regression
            // behind the sudden underruns / “packet loss”.
            try? session.setPreferredIOBufferDuration(0.010)
            try session.setActive(true)
        } catch {
            DispatchQueue.main.async {
                self.statusText = "音频会话初始化失败：\(error.localizedDescription)"
            }
        }
    }

    private func deactivateAudioSession() {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func installObservers() {
        let center = NotificationCenter.default
        observers.append(center.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            self?.handleInterruption(note)
        })
        observers.append(center.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            self?.handleRouteChange(note)
        })
        observers.append(center.addObserver(
            forName: AVAudioSession.mediaServicesWereResetNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            self.activateAudioSession()
            self.statusText = "音频服务已重置，正在恢复…"
            self.netQueue.async {
                self.currentStreamID = ""
                self.pipeline.stop()
            }
        })
    }

    private func handleInterruption(_ note: Notification) {
        guard let info = note.userInfo,
              let raw = info[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }

        switch type {
        case .began:
            pipeline.suspend()
            statusText = "音频被系统占用，恢复后继续"
        case .ended:
            activateAudioSession()
            pipeline.resume()
            statusText = "正在恢复音频…"
        @unknown default:
            break
        }
    }

    private func handleRouteChange(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: raw) else { return }
        if reason == .oldDeviceUnavailable {
            statusText = "音频输出已切换"
        }
    }
}
