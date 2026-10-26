package com.wilsonfd.airwave

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Process
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.TreeMap
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * UDP PCM player for Android.
 *
 * AudioTrack is fed one packet at a time from a sequence-number jitter buffer.
 * The track buffer is intentionally only a few packets; the pre-buffer is
 * separate, so latency stays close to the selected mode.
 */
class AudioEngine(private val callback: Callback) {

    interface Callback {
        fun onFirstPacket()
        fun onAudioStats(stats: CoreStats)
    }

    private val lock = Object()
    private var track: AudioTrack? = null
    private var playback: Thread? = null
    private var statsThread: Thread? = null

    @Volatile private var running = false
    private var primed = false

    private var sampleRate = 48_000
    private var channels = 2
    private var packetFrames = 336
    private var packetMs = 7.0
    private var packetBytes = 336 * 2 * 2
    private var mode = LatencyMode.AUTO
    private var adaptiveMs = 70

    private var jitter = JitterBuffer()
    private var lastPcm: ByteArray? = null
    private var concealRun = 0

    private var received = 0
    private var lost = 0
    private var trimmed = 0
    private var underruns = 0
    private var lastUnderrunAt = 0L
    private var lastLossAt = 0L
    private var lastAdaptAt = 0L
    private var lastStatsAt = 0L
    private var announced = false
    private var smoothedLevel = 0f

    fun configure(
        rate: Double,
        channelCount: Int,
        frames: Int,
        ms: Double,
        streamId: String,
        newMode: LatencyMode
    ) {
        stopLocked()
        synchronized(lock) {
            sampleRate = rate.toInt().coerceIn(8_000, 192_000)
            channels = channelCount.coerceIn(1, 2)
            packetFrames = max(1, frames)
            packetMs = if (ms > 0) ms else 7.0
            packetBytes = packetFrames * channels * 2
            mode = newMode
            adaptiveMs = newMode.prebufferMs
            jitter = JitterBuffer()
            primed = false
            announced = false
            lastPcm = null
            concealRun = 0
            received = 0
            lost = 0
            trimmed = 0
            underruns = 0
            lastUnderrunAt = 0
            lastLossAt = 0
            lastAdaptAt = System.currentTimeMillis()
            lastStatsAt = 0
        }
        val t = buildTrack()
        synchronized(lock) { track = t }
        startThreads()
    }

    fun setMode(newMode: LatencyMode) {
        synchronized(lock) {
            if (mode == newMode) return
            mode = newMode
            adaptiveMs = newMode.prebufferMs
            // Discard the old playback queue so the new target takes effect
            // immediately instead of waiting for 100+ ms of stale audio.
            primed = false
            jitter = JitterBuffer()
            lastPcm = null
            concealRun = 0
            try {
                track?.pause()
                track?.flush()
                track?.play()
            } catch (_: Exception) {
            }
            lock.notifyAll()
        }
    }

    fun push(seq: Int, pcm: ByteArray) {
        synchronized(lock) {
            if (!running) return
            if (pcm.size != packetBytes) return
            if (!jitter.insert(seq, pcm)) return
            received++
            lastPcm = pcm
            val lvl = rmsLevel(pcm)
            smoothedLevel = if (lvl > smoothedLevel) {
                smoothedLevel * 0.55f + lvl * 0.45f
            } else {
                smoothedLevel * 0.88f + lvl * 0.12f
            }
            val target = targetPacketsLocked()
            if (!primed && jitter.count >= target) {
                primed = true
                lock.notifyAll()
            }
            if (primed) {
                // Clock drift correction: keep the total queue near the target.
                val maxPackets = target + 10
                if (jitter.count > maxPackets) {
                    val dropped = jitter.trimTo(target)
                    trimmed += dropped
                    lastPcm = null
                }
            }
        }
    }

    fun stop() {
        stopLocked()
    }

    private fun stopLocked() {
        running = false
        synchronized(lock) { lock.notifyAll() }
        try { playback?.join(800) } catch (_: InterruptedException) {}
        try { statsThread?.join(500) } catch (_: InterruptedException) {}
        playback = null
        statsThread = null
        synchronized(lock) {
            try {
                track?.pause()
                track?.flush()
                track?.stop()
                track?.release()
            } catch (_: Exception) {
            }
            track = null
            primed = false
            jitter = JitterBuffer()
            lastPcm = null
        }
    }

    private fun buildTrack(): AudioTrack {
        val channelMask =
            if (channels >= 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val minBytes = AudioTrack.getMinBufferSize(
            sampleRate, channelMask, AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(packetBytes * 2)
        val bufferBytes = max(minBytes, packetBytes * 4)
        val attrs = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
            .build()
        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(sampleRate)
            .setChannelMask(channelMask)
            .build()
        val builder = AudioTrack.Builder()
            .setAudioAttributes(attrs)
            .setAudioFormat(format)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setBufferSizeInBytes(bufferBytes)
        try {
            builder.setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
        } catch (_: Throwable) {
        }
        return try {
            builder.build()
        } catch (_: Throwable) {
            AudioTrack.Builder()
                .setAudioAttributes(attrs)
                .setAudioFormat(format)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setBufferSizeInBytes(max(minBytes, packetBytes * 6))
                .build()
        }
    }

    private fun startThreads() {
        running = true
        playback = Thread({ playbackLoop() }, "airwave-audio").also { it.start() }
        statsThread = Thread({ statsLoop() }, "airwave-stats").also { it.start() }
    }

    private fun playbackLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        val t = synchronized(lock) { track } ?: return
        try { t.play() } catch (_: Exception) { return }
        while (running) {
            var packet: ByteArray? = null
            synchronized(lock) {
                if (!primed) {
                    try { lock.wait(20) } catch (_: InterruptedException) {}
                    return@synchronized
                }
                val p = jitter.consume()
                if (p != null) {
                    concealRun = 0
                    if (!announced) {
                        announced = true
                        callback.onFirstPacket()
                    }
                    packet = p
                } else if (jitter.count == 0) {
                    val now = System.currentTimeMillis()
                    if (now - lastUnderrunAt > 1_000) underruns++
                    lastUnderrunAt = now
                    try { lock.wait(2) } catch (_: InterruptedException) {}
                } else {
                    jitter.skip()
                    lost++
                    lastLossAt = System.currentTimeMillis()
                    packet = concealLocked()
                }
            }
            val p = packet ?: continue
            try {
                val written = t.write(p, 0, p.size, AudioTrack.WRITE_BLOCKING)
                if (written <= 0) {
                    synchronized(lock) {
                        underruns++
                        lastUnderrunAt = System.currentTimeMillis()
                    }
                }
            } catch (_: Exception) {
                if (running) {
                    synchronized(lock) {
                        underruns++
                        lastUnderrunAt = System.currentTimeMillis()
                    }
                }
            }
        }
    }

    private fun statsLoop() {
        while (running) {
            try { Thread.sleep(500) } catch (_: InterruptedException) { return }
            val stats: CoreStats
            synchronized(lock) {
                val now = System.currentTimeMillis()
                if (mode == LatencyMode.AUTO) {
                    val recentUnderrun = now - lastUnderrunAt < 4_000
                    if (recentUnderrun && now - lastAdaptAt > 1_500) {
                        adaptiveMs = min(140, adaptiveMs + 10)
                        lastAdaptAt = now
                    } else if (!recentUnderrun && now - lastAdaptAt > 8_000 && adaptiveMs > 35) {
                        adaptiveMs = max(35, adaptiveMs - 5)
                        lastAdaptAt = now
                    }
                }
                val buffered = (jitter.count + (if (primed) 2 else 0)) * packetMs
                val total = received + lost
                val loss = if (total > 0) lost.toDouble() / total * 100.0 else 0.0
                stats = CoreStats(
                    bufferMs = buffered.roundToInt(),
                    lossPercent = loss,
                    underruns = underruns,
                    received = received,
                    trimmed = trimmed,
                    latencyMs = buffered.roundToInt() + 20,
                    level = smoothedLevel
                )
                lastStatsAt = now
            }
            callback.onAudioStats(stats)
        }
    }

    private fun targetPacketsLocked(): Int {
        val ms = if (mode == LatencyMode.AUTO) adaptiveMs else mode.prebufferMs
        return max(1, (ms / packetMs).roundToInt())
    }

    private fun rmsLevel(pcm: ByteArray): Float {
        if (pcm.size < 2) return 0f
        var sum = 0.0
        var samples = 0
        var i = 0
        while (i + 1 < pcm.size) {
            val v = ((pcm[i].toInt() and 0xFF) or (pcm[i + 1].toInt() shl 8)).toShort().toDouble()
            sum += v * v
            samples++
            i += 2
        }
        if (samples == 0) return 0f
        val rms = kotlin.math.sqrt(sum / samples)
        return (rms / 9000.0).coerceIn(0.0, 1.0).toFloat()
    }

    private fun concealLocked(): ByteArray {
        val base = lastPcm
        if (base == null || base.size != packetBytes) {
            concealRun++
            return ByteArray(packetBytes)
        }
        val out = base.copyOf()
        val gain = max(0.0, 0.65 - 0.2 * concealRun)
        concealRun++
        val bb = ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN)
        var i = 0
        while (i + 1 < out.size) {
            val v = bb.getShort(i)
            bb.putShort(i, (v * gain).toInt().toShort())
            i += 2
        }
        return out
    }
}

/** Sequence-number buffer that tolerates duplicates, reordering and loss. */
private class JitterBuffer {
    private val packets = TreeMap<Long, ByteArray>()
    private var expected = 0L
    private var started = false
    private var lastRaw: Int? = null
    private var high = 0L

    val count: Int get() = packets.size

    fun insert(rawSeq: Int, pcm: ByteArray): Boolean {
        val seq = unwrap(rawSeq)
        if (!started) {
            started = true
            expected = seq
        }
        if (seq < expected - 100) return false
        if (packets.containsKey(seq)) return false
        packets[seq] = pcm
        return true
    }

    fun consume(): ByteArray? {
        val p = packets.remove(expected) ?: return null
        expected++
        return p
    }

    fun skip() {
        packets.remove(expected)
        expected++
    }

    fun trimTo(target: Int): Int {
        var dropped = 0
        while (packets.size > target && packets.isNotEmpty()) {
            packets.remove(expected)
            expected++
            dropped++
        }
        return dropped
    }

    private fun unwrap(raw: Int): Long {
        val prev = lastRaw
        if (prev == null) {
            lastRaw = raw
            return raw.toLong() and 0xFFFFFFFFL
        }
        val diff = raw - prev
        if (diff < -0x40000000) high += 0x100000000L
        else if (diff > 0x40000000) high -= 0x100000000L
        lastRaw = raw
        return high + (raw.toLong() and 0xFFFFFFFFL)
    }
}
