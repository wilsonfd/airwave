package com.wilsonfd.airwave

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException
import kotlin.math.max

data class StreamMeta(
    val rate: Double,
    val channels: Int,
    val packetFrames: Int,
    val packetMs: Double,
    val streamId: String,
    val codec: String,
    val name: String
)

/**
 * UDP receiver. The PC starts sending audio as soon as it sees HELLO; the
 * receive loop is completely independent from the audio thread.
 */
class UdpClient(
    private val host: String,
    private val port: Int,
    private val listener: Listener
) {

    interface Listener {
        fun onMeta(meta: StreamMeta)
        fun onAudio(seq: Int, pcm: ByteArray)
        fun onWaiting(reason: String)
        fun onError(message: String)
    }

    @Volatile private var running = false
    private var thread: Thread? = null
    @Volatile private var socket: DatagramSocket? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread({ loop() }, "airwave-udp").also { it.start() }
    }

    fun stop() {
        running = false
        try {
            val s = socket
            if (s != null && !s.isClosed) {
                val bye = "BYE".toByteArray(Charsets.UTF_8)
                s.send(
                    DatagramPacket(
                        bye, bye.size,
                        InetAddress.getByName(host), port
                    )
                )
            }
        } catch (_: Exception) {
        }
        try { socket?.close() } catch (_: Exception) {}
        try { thread?.join(700) } catch (_: InterruptedException) {}
        thread = null
        socket = null
    }

    private fun loop() {
        var lastHello = 0L
        var lastPacket = 0L
        var warned = false
        while (running) {
            var s: DatagramSocket? = null
            try {
                s = DatagramSocket()
                s.soTimeout = 500
                try { s.trafficClass = 0xB8 } catch (_: Exception) {}
                socket = s
                val address = InetAddress.getByName(host)
                lastHello = 0L
                lastPacket = System.currentTimeMillis()
                warned = false
                val buffer = ByteArray(4096)

                while (running) {
                    val now = System.currentTimeMillis()
                    if (now - lastHello >= 750) {
                        val hello = "HELLO".toByteArray(Charsets.UTF_8)
                        s.send(DatagramPacket(hello, hello.size, address, port))
                        lastHello = now
                    }

                    val packet = DatagramPacket(buffer, buffer.size)
                    try {
                        s.receive(packet)
                    } catch (_: SocketTimeoutException) {
                        if (!warned && System.currentTimeMillis() - lastPacket > 8_000) {
                            warned = true
                            listener.onWaiting("电脑暂时没有响应")
                        }
                        continue
                    }

                    lastPacket = System.currentTimeMillis()
                    warned = false
                    val data = packet.data
                    val len = packet.length
                    if (len <= 0) continue
                    when (data[0].toInt() and 0xFF) {
                        1 -> {
                            if (len < 3) continue
                            val metaLen = ((data[1].toInt() and 0xFF) shl 8) or
                                (data[2].toInt() and 0xFF)
                            if (metaLen <= 0 || 3 + metaLen > len) continue
                            try {
                                val json = String(data, 3, metaLen, Charsets.UTF_8)
                                val obj = JSONObject(json)
                                val meta = StreamMeta(
                                    rate = obj.optDouble("rate", 48_000.0),
                                    channels = obj.optInt("channels", 2).coerceIn(1, 2),
                                    packetFrames = obj.optInt("packet_frames", 0)
                                        .let { if (it > 0) it else max(1, (48_000 * 0.007).toInt()) },
                                    packetMs = obj.optDouble("packet_ms", 7.0),
                                    streamId = obj.optString("stream_id", ""),
                                    codec = obj.optString("codec", "pcm_s16le"),
                                    name = obj.optString("name", "PC")
                                )
                                listener.onMeta(meta)
                            } catch (_: Exception) {
                                // Ignore a malformed META and keep receiving.
                            }
                        }

                        2 -> {
                            if (len < 5) continue
                            val seq = ((data[1].toInt() and 0xFF) shl 24) or
                                ((data[2].toInt() and 0xFF) shl 16) or
                                ((data[3].toInt() and 0xFF) shl 8) or
                                (data[4].toInt() and 0xFF)
                            listener.onAudio(seq, data.copyOfRange(5, len))
                        }
                    }
                }
            } catch (e: Exception) {
                if (!running) break
                listener.onError(e.localizedMessage ?: "网络错误")
                try { Thread.sleep(1_000) } catch (_: InterruptedException) { break }
            } finally {
                try { s?.close() } catch (_: Exception) {}
                if (socket === s) socket = null
            }
        }
    }
}
