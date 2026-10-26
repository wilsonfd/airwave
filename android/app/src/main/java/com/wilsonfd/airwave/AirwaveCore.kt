package com.wilsonfd.airwave

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Process-wide streaming core. The Activity and the foreground Service both
 * talk to this object, so rotating / closing the UI does not interrupt audio.
 */
object AirwaveCore {

    private val listeners = CopyOnWriteArrayList<CoreListener>()
    private val main = Handler(Looper.getMainLooper())

    private var appContext: Context? = null
    private var udp: UdpClient? = null
    private var audio: AudioEngine? = null

    private var currentStreamId = ""
    private var currentFormat = ""
    private var wifiLock: WifiManager.WifiLock? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var focusRequest: AudioFocusRequest? = null
    private var audioManager: AudioManager? = null

    @Volatile private var state = CoreState()
    @Volatile private var stats = CoreStats()

    fun init(context: Context) {
        if (appContext == null) {
            appContext = context.applicationContext
            Prefs.init(context)
            state = state.copy(
                host = Prefs.host,
                port = Prefs.port,
                mode = Prefs.mode
            )
        }
    }

    fun addListener(listener: CoreListener) {
        if (!listeners.contains(listener)) listeners.add(listener)
        main.post {
            listener.onCoreState(state)
            listener.onCoreStats(stats)
        }
    }

    fun removeListener(listener: CoreListener) {
        listeners.remove(listener)
    }

    fun currentState(): CoreState = state
    fun currentStats(): CoreStats = stats
    fun isActive(): Boolean = udp != null

    @Synchronized
    fun connect(host: String, port: Int, mode: LatencyMode) {
        val ctx = appContext ?: return
        val cleanHost = host.trim()
        if (cleanHost.isEmpty() || port !in 1024..65535) {
            updateState(Phase.IDLE, "请先在设置里填写电脑 IP")
            return
        }
        disconnectInternal()
        Prefs.host = cleanHost
        Prefs.port = port
        Prefs.mode = mode
        acquireLocks(ctx)

        currentStreamId = ""
        currentFormat = ""
        val engine = AudioEngine(object : AudioEngine.Callback {
            override fun onFirstPacket() {
                updateState(Phase.PLAYING, "正在播放")
            }

            override fun onAudioStats(s: CoreStats) {
                stats = s
                notifyStats()
            }
        })
        audio = engine

        val client = UdpClient(cleanHost, port, object : UdpClient.Listener {
            override fun onMeta(meta: StreamMeta) {
                val key = "${meta.rate}/${meta.channels}/${meta.packetFrames}/${meta.streamId}"
                if (key != currentFormat) {
                    currentFormat = key
                    currentStreamId = meta.streamId
                    engine.configure(
                        meta.rate, meta.channels, meta.packetFrames,
                        meta.packetMs, meta.streamId, Prefs.mode
                    )
                    val ch = if (meta.channels >= 2) "立体声" else "单声道"
                    updateState(
                        Phase.WAITING,
                        "已连接，等待电脑播放声音",
                        format = "${meta.rate.toInt()} Hz · $ch · ${String.format("%.1f", meta.packetMs)} ms"
                    )
                } else if (state.phase == Phase.CONNECTING) {
                    updateState(Phase.WAITING, "已连接，等待电脑播放声音")
                }
            }

            override fun onAudio(seq: Int, pcm: ByteArray) {
                engine.push(seq, pcm)
            }

            override fun onWaiting(reason: String) {
                if (state.phase == Phase.PLAYING) {
                    updateState(Phase.WAITING, reason)
                }
            }

            override fun onError(message: String) {
                if (state.phase != Phase.IDLE) {
                    updateState(Phase.CONNECTING, "网络重连中：$message")
                }
            }
        })
        udp = client
        updateState(Phase.CONNECTING, "正在连接 $cleanHost:$port")
        client.start()
    }

    @Synchronized
    fun disconnect() {
        disconnectInternal()
        updateState(Phase.IDLE, "点上方圆钮开始连接")
    }

    @Synchronized
    fun setMode(mode: LatencyMode) {
        Prefs.mode = mode
        audio?.setMode(mode)
        updateState(state.phase, state.status, mode = mode, format = state.format)
    }

    fun currentMode(): LatencyMode = Prefs.mode

    private fun disconnectInternal() {
        try { udp?.stop() } catch (_: Exception) {}
        udp = null
        try { audio?.stop() } catch (_: Exception) {}
        audio = null
        currentStreamId = ""
        currentFormat = ""
        releaseLocks()
        stats = CoreStats()
        notifyStats()
    }

    private fun acquireLocks(context: Context) {
        try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            wifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "AirWave").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (_: Exception) {
        }
        try {
            val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AirWave:stream").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (_: Exception) {
        }
        try {
            val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
            audioManager = am
            val attrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build()
            val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(attrs)
                .setOnAudioFocusChangeListener { }
                .build()
            focusRequest = request
            am.requestAudioFocus(request)
        } catch (_: Exception) {
        }
    }

    private fun releaseLocks() {
        try { wifiLock?.release() } catch (_: Exception) {}
        wifiLock = null
        try { wakeLock?.release() } catch (_: Exception) {}
        wakeLock = null
        try {
            val req = focusRequest
            if (req != null) audioManager?.abandonAudioFocusRequest(req)
        } catch (_: Exception) {}
        focusRequest = null
        audioManager = null
    }

    private fun updateState(
        phase: Phase,
        status: String,
        mode: LatencyMode? = null,
        format: String? = null
    ) {
        state = state.copy(
            phase = phase,
            status = status,
            host = Prefs.host,
            port = Prefs.port,
            mode = mode ?: Prefs.mode,
            format = format ?: state.format
        )
        main.post { listeners.forEach { it.onCoreState(state) } }
    }

    private fun notifyStats() {
        main.post { listeners.forEach { it.onCoreStats(stats) } }
    }
}
