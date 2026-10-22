import AVFoundation
import Foundation

/// Owns AVAudioEngine and turns the UDP jitter buffer into a continuous stream
/// of scheduled PCM buffers.
///
/// The old implementation scheduled exactly one 5 ms buffer at a time and only
/// refilled when its completion handler fired.  Any scheduling hiccup therefore
/// produced an audible hole.  Here the player always keeps `leadBuffers`
/// queued, a 4 ms timer tops the queue up, and late packets get a short grace
/// period before concealment is scheduled.
final class AudioPipeline {
    struct Stats {
        var bufferMs: Double
        var latencyMs: Double
        var lossPercent: Double
        var underruns: Int
        var scheduled: Int
        var targetMs: Double
        var received: Int
    }

    enum Mode: String, CaseIterable {
        case auto
        case low
        case balanced
        case stable

        var prebufferMs: Double {
            switch self {
            case .auto: return 120
            case .low: return 45
            case .balanced: return 120
            case .stable: return 240
            }
        }

        var leadBuffers: Int {
            switch self {
            case .auto: return 14
            case .low: return 4
            case .balanced: return 14
            case .stable: return 18
            }
        }
    }

    private let queue = DispatchQueue(label: "com.wilsonfd.airwave.audio", qos: .userInteractive)
    private var engine: AVAudioEngine?
    private var player: AVAudioPlayerNode?
    private var mixer: AVAudioMixerNode?
    private var format: AVAudioFormat?
    private var tapInstalled = false
    private var generation: UInt64 = 0
    private var running = false
    private var paused = false

    private var sampleRate: Double = 48000
    private var channelCount: Int = 2
    private var packetFrames: Int = 336
    private var packetMs: Double = 7
    private var streamID = ""
    private var mode: Mode = .auto

    private var jitter = PacketJitterBuffer()
    private var lastGoodPCM: Data?
    private var concealRun = 0
    private var needsFadeIn = false
    private var didStart = false
    private var scheduled = 0
    private var recovering = false
    private var lastTrimAt = Date.distantPast

    private var pumpTimer: DispatchSourceTimer?
    private var statsTimer: DispatchSourceTimer?

    private var packetsReceived = 0
    private var packetsLost = 0
    private var underruns = 0
    private var adaptiveMs: Double = 120
    private var lastLossAt = Date.distantPast
    private var lastUnderrunAt = Date.distantPast
    private var lastAdaptAt = Date()
    private var lastArrival: Date?
    private var lastSeq: UInt32?
    private var arrivalJitterMs: Double = 0

    private var smoothedLevel: Float = 0
    private var levelPushCounter = 0

    var onLevel: ((Float) -> Void)?
    var onStarted: (() -> Void)?
    var onStats: ((Stats) -> Void)?
    var onError: ((String) -> Void)?
    var onAudioStopped: (() -> Void)?

    init() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(engineConfigurationChanged),
            name: .AVAudioEngineConfigurationChange,
            object: nil
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        pumpTimer?.cancel()
        statsTimer?.cancel()
        if tapInstalled {
            mixer?.removeTap(onBus: 0)
        }
        player?.stop()
        engine?.stop()
    }

    // MARK: - Public control

    func configure(sampleRate: Double, channels: Int, packetFrames: Int,
                   packetMs: Double, streamID: String, mode: Mode) {
        queue.async { [weak self] in
            guard let self = self else { return }
            self.generation &+= 1
            self.teardownLocked()
            self.sampleRate = max(8000, sampleRate)
            self.channelCount = max(1, min(2, channels))
            self.packetFrames = max(1, packetFrames)
            self.packetMs = packetMs > 0 ? packetMs : 7
            self.streamID = streamID
            self.mode = mode
            self.adaptiveMs = mode == .auto ? 120 : mode.prebufferMs
            self.resetBuffersLocked()
            self.buildEngineLocked()
            if self.engine != nil, self.player != nil {
                self.startPumpLocked()
                self.startStatsLocked()
            }
            self.paused = false
        }
    }

    func stop() {
        queue.async { [weak self] in
            guard let self = self else { return }
            self.generation &+= 1
            self.teardownLocked()
            DispatchQueue.main.async { self.onLevel?(0) }
        }
    }

    func suspend() {
        queue.async { [weak self] in
            guard let self = self, self.running else { return }
            self.paused = true
            self.player?.pause()
            self.resetBuffersLocked()
            self.scheduled = 0
            DispatchQueue.main.async { self.onLevel?(0) }
        }
    }

    func resume() {
        queue.async { [weak self] in
            guard let self = self, self.running else { return }
            self.paused = false
            if let engine = self.engine, !engine.isRunning {
                try? engine.start()
            }
            self.player?.play()
            self.resetBuffersLocked()
        }
    }

    func setMode(_ newMode: Mode) {
        queue.async { [weak self] in
            guard let self = self else { return }
            self.mode = newMode
            if newMode != .auto {
                self.adaptiveMs = newMode.prebufferMs
            }
        }
    }

    func ingest(seq: UInt32, pcm: Data) {
        queue.async { [weak self] in
            guard let self = self, self.running, !self.paused else { return }
            let expectedBytes = self.packetFrames * self.channelCount * 2
            guard pcm.count == expectedBytes else { return }

            if self.jitter.started {
                let ahead = PacketJitterBuffer.distance(from: self.jitter.expected, to: seq)
                if ahead > 400 || ahead < -200 {
                    // PC restarted its sequence counter (or we lost a huge run).
                    self.jitter.start(at: seq)
                    self.scheduled = 0
                    self.didStart = false
                } else if PacketJitterBuffer.isBefore(seq, self.jitter.expected) && self.jitter.primed {
                    // A late duplicate of an already consumed packet.
                    return
                }
            }
            // The PC intentionally sends every packet twice.  Do not count the
            // second copy as a received packet, otherwise the loss percentage
            // looks artificially low.
            if self.jitter.contains(seq) {
                return
            }

            self.packetsReceived += 1
            let now = Date()
            if let last = self.lastArrival {
                let deltaMs = now.timeIntervalSince(last) * 1000
                let deviation = abs(deltaMs - self.packetMs)
                self.arrivalJitterMs = self.arrivalJitterMs * 0.9 + deviation * 0.1
            }
            self.lastArrival = now
            self.lastSeq = seq
            self.jitter.insert(seq: seq, pcm: pcm)
            let primeTarget = self.recovering
                ? min(4, self.prebufferPackets)
                : self.prebufferPackets
            self.jitter.primeIfReady(primeTarget)
            if self.jitter.primed {
                self.recovering = false
            }
            self.pumpLocked()
        }
    }

    // MARK: - Engine

    private func buildEngineLocked() {
        // Match the proven Doubao audio path: interleaved Int16 PCM.  Float
        // buffers work in theory but add a conversion layer; Int16 is what the
        // working client used and is the safest choice for AVAudioPlayerNode.
        guard let fmt = AVAudioFormat(commonFormat: .pcmFormatInt16,
                                      sampleRate: sampleRate,
                                      channels: AVAudioChannelCount(channelCount),
                                      interleaved: true) else {
            DispatchQueue.main.async { self.onError?("不支持的音频格式") }
            return
        }

        let engine = AVAudioEngine()
        let player = AVAudioPlayerNode()
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: fmt)
        engine.mainMixerNode.outputVolume = 1

        let mixer = engine.mainMixerNode
        var tapFormat = mixer.outputFormat(forBus: 0)
        if tapFormat.sampleRate <= 0 || tapFormat.channelCount == 0 {
            tapFormat = fmt
        }
        mixer.installTap(onBus: 0, bufferSize: 512, format: tapFormat) { [weak self] buffer, _ in
            self?.handleTap(buffer)
        }
        tapInstalled = true

        self.engine = engine
        self.player = player
        self.mixer = mixer
        self.format = fmt
        self.running = true

        engine.prepare()
        do {
            try engine.start()
        } catch {
            self.running = false
            DispatchQueue.main.async { self.onError?("音频引擎启动失败：\(error.localizedDescription)") }
        }
    }

    private func teardownLocked() {
        running = false
        paused = false
        pumpTimer?.cancel()
        pumpTimer = nil
        statsTimer?.cancel()
        statsTimer = nil

        if tapInstalled {
            mixer?.removeTap(onBus: 0)
            tapInstalled = false
        }
        player?.stop()
        engine?.stop()
        if let player = player, let engine = engine {
            engine.detach(player)
        }
        player = nil
        engine = nil
        mixer = nil
        format = nil
        scheduled = 0
        didStart = false
        concealRun = 0
        needsFadeIn = false
        lastGoodPCM = nil
        jitter.reset()
        smoothedLevel = 0
    }

    private func resetBuffersLocked() {
        jitter.reset()
        scheduled = 0
        didStart = false
        concealRun = 0
        needsFadeIn = false
        lastGoodPCM = nil
        packetsReceived = 0
        packetsLost = 0
        underruns = 0
        arrivalJitterMs = 0
        lastArrival = nil
        lastSeq = nil
        recovering = false
        lastTrimAt = Date.distantPast
        lastUnderrunAt = Date.distantPast
        lastLossAt = Date.distantPast
        adaptiveMs = mode == .auto ? 120 : mode.prebufferMs
        lastAdaptAt = Date()
    }

    @objc private func engineConfigurationChanged() {
        // Do NOT tear the pipeline down here.  A configuration change callback
        // can arrive more than once (route change, session reconfiguration),
        // and rebuilding resets the jitter buffer -> a guaranteed audible gap.
        // If the engine actually stopped, just restart it in place.
        queue.async { [weak self] in
            guard let self = self, self.running, let engine = self.engine else { return }
            if !engine.isRunning {
                try? engine.start()
                self.player?.play()
            }
        }
    }

    private func startPumpLocked() {
        pumpTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now(), repeating: .milliseconds(4), leeway: .milliseconds(1))
        timer.setEventHandler { [weak self] in
            self?.pumpLocked()
        }
        timer.resume()
        pumpTimer = timer
    }

    private func startStatsLocked() {
        statsTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + 0.5, repeating: .milliseconds(500), leeway: .milliseconds(80))
        timer.setEventHandler { [weak self] in
            self?.emitStatsLocked()
        }
        timer.resume()
        statsTimer = timer
    }

    // MARK: - Buffering

    private var prebufferMs: Double {
        mode == .auto ? adaptiveMs : mode.prebufferMs
    }

    private var prebufferPackets: Int {
        max(2, Int(round(prebufferMs / max(1, packetMs))))
    }

    private var leadBuffers: Int {
        mode.leadBuffers
    }

    private func pumpLocked() {
        guard running, !paused, let player = player, let fmt = format, jitter.primed else { return }

        // Bound the TOTAL queued audio, not just the jitter dictionary.  The
        // player already holds `scheduled` buffers, so comparing only
        // jitter.count against prebuffer + lead allowed hundreds of ms of
        // drift to accumulate before anything was trimmed.
        let targetBuffered = prebufferPackets + 6   // ~30–40 ms of slack
        let bufferedPackets = jitter.count + scheduled
        if bufferedPackets > targetBuffered,
           Date().timeIntervalSince(lastTrimAt) > 1.0 {
            let excess = min(8, bufferedPackets - targetBuffered)
            var dropped = 0
            while dropped < excess, jitter.count > 0 {
                jitter.skipExpected()
                dropped += 1
            }
            if dropped > 0 {
                packetsLost += dropped
                needsFadeIn = true
                lastTrimAt = Date()
            }
        }

        var guardCount = 0
        while scheduled < leadBuffers {
            guardCount += 1
            if guardCount > 16 { break }

            if let pcm = jitter.consumeExpected() {
                lastGoodPCM = pcm
                concealRun = 0
                let starting = scheduled == 0
                schedulePCM(pcm, format: fmt, player: player, fadeIn: needsFadeIn)
                needsFadeIn = false
                scheduled += 1
                if starting {
                    didStart = true
                    onStarted?()
                }
                continue
            }

            // Nothing at `expected`.
            if scheduled == 0 {
                underruns += 1
                lastUnderrunAt = Date()
                if jitter.count == 0 {
                    // The network is quiet; wait for a short recovery
                    // pre-buffer rather than filling the queue with
                    // concealment.
                    jitter.unprime()
                    recovering = true
                    return
                }
                // Future packets are already waiting, so the expected one is
                // lost.  Skip it and recover immediately.
                packetsLost += 1
                lastLossAt = Date()
                jitter.skipExpected()
                continue
            }
            if scheduled > 2 {
                // A late packet still has a few milliseconds to arrive.
                break
            }

            let pcm = concealmentPCM()
            schedulePCM(pcm, format: fmt, player: player, fadeIn: false)
            scheduled += 1
            packetsLost += 1
            concealRun += 1
            needsFadeIn = true
            lastLossAt = Date()
        }

        // Match the known-good Doubao flow: queue a burst first, then start the
        // player.  Playing an empty node and scheduling into it is allowed, but
        // this ordering has fewer edge cases on older iOS versions.
        if !player.isPlaying, scheduled > 0 {
            player.play()
        }
    }

    private func concealmentPCM() -> Data {
        let bytes = packetFrames * channelCount * 2
        var output = Data(count: bytes)
        guard let last = lastGoodPCM, last.count == bytes, concealRun < 3 else {
            return output
        }
        let gain = max(0.0, 0.65 - 0.2 * Double(concealRun))
        output.withUnsafeMutableBytes { dstRaw in
            last.withUnsafeBytes { srcRaw in
                let dst = dstRaw.bindMemory(to: Int16.self)
                let src = srcRaw.bindMemory(to: Int16.self)
                for i in 0..<src.count {
                    dst[i] = Int16(Double(src[i]) * gain)
                }
            }
        }
        return output
    }

    private func schedulePCM(_ pcm: Data, format fmt: AVAudioFormat,
                             player: AVAudioPlayerNode, fadeIn: Bool) {
        guard let buffer = AVAudioPCMBuffer(pcmFormat: fmt,
                                            frameCapacity: AVAudioFrameCount(packetFrames)) else {
            return
        }
        buffer.frameLength = AVAudioFrameCount(packetFrames)
        let channels = Int(fmt.channelCount)
        let frames = packetFrames
        let fadeFrames = min(64, frames)
        let sampleCount = frames * channels

        pcm.withUnsafeBytes { raw in
            let src = raw.bindMemory(to: Int16.self)
            guard src.count >= sampleCount,
                  let dst = buffer.int16ChannelData?.pointee else { return }

            if fadeIn {
                // De-click after a concealment; the first 1–2 ms fades in.
                for i in 0..<sampleCount {
                    let frame = i / channels
                    var value = src[i]
                    if frame < fadeFrames {
                        value = Int16(Double(value) * Double(frame) / Double(fadeFrames))
                    }
                    dst[i] = value
                }
            } else {
                dst.update(from: src.baseAddress!, count: sampleCount)
            }
        }

        let gen = generation
        // Refill as soon as the buffer is consumed.  `.dataPlayedBack` only
        // fires after the buffer has finished playing, which leaves the queue
        // with less lookahead and is a classic cause of periodic underruns.
        player.scheduleBuffer(buffer, at: nil, options: [],
                              completionCallbackType: .dataConsumed) { [weak self] _ in
            guard let self = self else { return }
            self.queue.async {
                guard self.generation == gen else { return }
                self.scheduled = max(0, self.scheduled - 1)
                self.pumpLocked()
            }
        }
    }

    private func emitStatsLocked() {
        let now = Date()
        if mode == .auto {
            // Only an actual underrun proves the buffer is too small.  Packet
            // loss alone is handled by concealment and must not make latency
            // creep upward forever (that was the "starts fast, gets slower"
            // behaviour).  Also decay sooner and cap lower.
            let recentUnderrun = now.timeIntervalSince(lastUnderrunAt) < 4.0
            if recentUnderrun && now.timeIntervalSince(lastAdaptAt) > 1.5 {
                adaptiveMs = min(240, adaptiveMs + 20)
                lastAdaptAt = now
            } else if !recentUnderrun && now.timeIntervalSince(lastAdaptAt) > 8,
                      adaptiveMs > 90 {
                adaptiveMs = max(90, adaptiveMs - 6)
                lastAdaptAt = now
            }
        }

        let buffered = Double(jitter.count + scheduled) * packetMs
        let total = packetsReceived + packetsLost
        let loss = total > 0 ? Double(packetsLost) / Double(total) * 100.0 : 0.0
        let stats = Stats(
            bufferMs: buffered,
            latencyMs: buffered + 12,
            lossPercent: loss,
            underruns: underruns,
            scheduled: scheduled,
            targetMs: prebufferMs,
            received: packetsReceived
        )
        onStats?(stats)
    }

    // MARK: - Metering

    private func handleTap(_ buffer: AVAudioPCMBuffer) {
        guard let channel = buffer.floatChannelData?[0] else { return }
        let frames = Int(buffer.frameLength)
        guard frames > 0 else { return }

        var sum: Float = 0
        var i = 0
        while i < frames {
            let sample = channel[i]
            sum += sample * sample
            i += 2
        }
        let count = max(1, frames / 2)
        let rms = sqrt(sum / Float(count))
        let mapped = Float(min(1.0, pow(Double(max(0, rms * 5.0)), 0.8)))
        smoothedLevel = max(mapped, smoothedLevel * 0.86)

        levelPushCounter += 1
        if levelPushCounter >= 6 {
            levelPushCounter = 0
            let value = smoothedLevel
            DispatchQueue.main.async { [weak self] in
                self?.onLevel?(value)
            }
        }
    }
}
