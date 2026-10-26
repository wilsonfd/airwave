package com.wilsonfd.airwave

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

const val APP_VERSION = "2.2.0"
const val APP_BUILD = 7

enum class LatencyMode(
    val key: String,
    val label: String,
    val chip: String,
    val prebufferMs: Int,
    val subtitle: String
) {
    AUTO("auto", "自动", "自动", 70, "按抖动自动调整"),
    LOW("low", "低延迟", "低延迟", 35, "约 70–100 ms"),
    ULTRA("ultra", "极低延迟", "极低", 21, "约 45–70 ms，实验"),
    BALANCED("balanced", "平衡", "平衡", 70, "约 100–140 ms"),
    STABLE("stable", "稳定", "稳定", 140, "约 160–220 ms");

    companion object {
        fun fromKey(key: String?): LatencyMode =
            entries.firstOrNull { it.key == key } ?: AUTO
    }
}

data class Endpoint(val host: String, val port: Int, val lastUsed: Long) {
    val id: String get() = "${host.lowercase()}:$port"
}

object Prefs {
    private const val NAME = "airwave"
    private const val KEY_HOST = "host"
    private const val KEY_PORT = "port"
    private const val KEY_MODE = "mode"
    private const val KEY_SAVED = "saved_endpoints"
    private const val MAX_SAVED = 8

    private lateinit var sp: SharedPreferences

    fun init(context: Context) {
        if (!::sp.isInitialized) {
            sp = context.applicationContext.getSharedPreferences(NAME, Context.MODE_PRIVATE)
        }
    }

    var host: String
        get() = sp.getString(KEY_HOST, "") ?: ""
        set(value) = sp.edit().putString(KEY_HOST, value.trim()).apply()

    var port: Int
        get() = sp.getInt(KEY_PORT, 13666)
        set(value) = sp.edit().putInt(KEY_PORT, value).apply()

    var mode: LatencyMode
        get() = LatencyMode.fromKey(sp.getString(KEY_MODE, LatencyMode.AUTO.key))
        set(value) = sp.edit().putString(KEY_MODE, value.key).apply()

    fun saved(): List<Endpoint> {
        val raw = sp.getString(KEY_SAVED, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).mapNotNull { i ->
                val o = arr.optJSONObject(i) ?: return@mapNotNull null
                val host = o.optString("host", "").trim()
                val port = o.optInt("port", 0)
                if (host.isEmpty() || port !in 1024..65535) null
                else Endpoint(host, port, o.optLong("lastUsed", 0L))
            }.sortedByDescending { it.lastUsed }.take(MAX_SAVED)
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun saveSaved(items: List<Endpoint>): List<Endpoint> {
        val trimmed = items.sortedByDescending { it.lastUsed }.take(MAX_SAVED)
        val arr = JSONArray()
        trimmed.forEach {
            arr.put(JSONObject().put("host", it.host).put("port", it.port).put("lastUsed", it.lastUsed))
        }
        sp.edit().putString(KEY_SAVED, arr.toString()).apply()
        return trimmed
    }

    fun addSaved(host: String, port: Int): List<Endpoint> {
        val cleaned = host.trim()
        if (cleaned.isEmpty() || port !in 1024..65535) return saved()
        val next = saved().filterNot {
            it.host.equals(cleaned, ignoreCase = true) && it.port == port
        }.toMutableList()
        next.add(0, Endpoint(cleaned, port, System.currentTimeMillis()))
        return saveSaved(next)
    }

    fun removeSaved(id: String): List<Endpoint> =
        saveSaved(saved().filterNot { it.id == id })
}
