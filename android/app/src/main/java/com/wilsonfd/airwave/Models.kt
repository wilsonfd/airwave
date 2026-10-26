package com.wilsonfd.airwave

enum class Phase { IDLE, CONNECTING, WAITING, PLAYING }

data class CoreState(
    val phase: Phase = Phase.IDLE,
    val status: String = "点上方圆钮开始连接",
    val host: String = "",
    val port: Int = 13666,
    val mode: LatencyMode = LatencyMode.AUTO,
    val format: String = "",
    val version: String = APP_VERSION
)

data class CoreStats(
    val bufferMs: Int = 0,
    val lossPercent: Double = 0.0,
    val underruns: Int = 0,
    val received: Int = 0,
    val trimmed: Int = 0,
    val latencyMs: Int = 0,
    val level: Float = 0f
)

interface CoreListener {
    fun onCoreState(state: CoreState)
    fun onCoreStats(stats: CoreStats)
}
