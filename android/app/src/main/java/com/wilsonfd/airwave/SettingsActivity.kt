package com.wilsonfd.airwave

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class SettingsActivity : Activity() {

    private lateinit var ipField: EditText
    private lateinit var portField: EditText
    private lateinit var savedBox: LinearLayout
    private lateinit var modeBar: ModeBar
    private lateinit var modeHint: TextView
    private lateinit var errorText: TextView
    private var mode = LatencyMode.AUTO

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(applicationContext)
        mode = Prefs.mode
        window.statusBarColor = AwColor.BG
        window.navigationBarColor = AwColor.BG
        buildUi()
    }

    private fun buildUi() {
        val root = FrameLayout(this)
        root.addView(AuroraView(this), FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT
        ))
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            overScrollMode = View.OVER_SCROLL_NEVER
        }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20f), dp(22f), dp(20f), dp(34f))
        }
        scroll.addView(col, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT
        ))
        root.addView(scroll, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT
        ))
        setContentView(root)

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val cancel = awText(this, "取消", 12f, AwColor.MUTED, medium = true).apply {
            setPadding(dp(8f), dp(8f), dp(8f), dp(8f))
            setOnClickListener { finish() }
        }
        header.addView(cancel)
        val title = awText(this, "设置", 19f, AwColor.TEXT, medium = true).apply {
            gravity = Gravity.CENTER
        }
        header.addView(title, LinearLayout.LayoutParams(
            0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
        ))
        val saveTop = awText(this, "完成", 12f, AwColor.ACCENT, medium = true).apply {
            setPadding(dp(8f), dp(8f), dp(8f), dp(8f))
            setOnClickListener { saveAndFinish() }
        }
        header.addView(saveTop)
        col.addView(header)
        col.addView(space(12f))

        val conn = GlassCard(this)
        conn.addView(awText(this, "电脑连接", 10f, AwColor.DIM, medium = true))
        ipField = field("电脑 IP，例如 192.168.1.10", Prefs.host, InputType.TYPE_CLASS_TEXT)
        portField = field("端口", Prefs.port.toString(), InputType.TYPE_CLASS_NUMBER)
        conn.addView(ipField, fieldParams())
        conn.addView(portField, fieldParams())
        val saveIp = awText(this, "保存此地址", 11f, AwColor.ACCENT, medium = true).apply {
            setPadding(dp(12f), dp(7f), dp(12f), dp(7f))
            background = pillDrawable(
                this@SettingsActivity,
                Color.argb(24, 106, 169, 255), Color.argb(80, 106, 169, 255), 16f
            )
            setOnClickListener { saveEndpointOnly() }
        }
        conn.addView(saveIp, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(10f), 0, 0) })

        errorText = awText(this, "", 10f, AwColor.RED).apply {
            setPadding(0, dp(6f), 0, 0)
        }
        conn.addView(errorText)
        col.addView(conn)
        col.addView(space(14f))

        val savedCard = GlassCard(this)
        val savedHead = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        savedHead.addView(awText(this, "已保存的电脑", 10f, AwColor.DIM, medium = true), LinearLayout.LayoutParams(
            0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
        ))
        savedHead.addView(awText(this, "点击填入", 9f, AwColor.DIM))
        savedCard.addView(savedHead)
        savedBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(6f), 0, 0)
        }
        savedCard.addView(savedBox)
        col.addView(savedCard)
        col.addView(space(14f))

        val latency = GlassCard(this)
        val latHead = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        latHead.addView(awText(this, "延迟模式", 10f, AwColor.DIM, medium = true), LinearLayout.LayoutParams(
            0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
        ))
        modeHint = awText(this, mode.subtitle, 9f, AwColor.MUTED)
        latHead.addView(modeHint)
        latency.addView(latHead)
        modeBar = ModeBar(this).apply {
            setSelected(mode)
            onSelect = {
                mode = it
                modeHint.text = it.subtitle
            }
        }
        latency.addView(modeBar, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(8f), 0, 0) })
        latency.addView(awText(
            this,
            "推荐：PC 7ms + 极低延迟；5ms 包率更高，弱网反而容易丢。",
            9f, AwColor.DIM
        ).apply { setPadding(0, dp(8f), 0, 0) })
        col.addView(latency)
        col.addView(space(18f))

        val apply = awText(this, "保存并连接", 15f, AwColor.BG, medium = true).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(14f), 0, dp(14f))
            background = GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                intArrayOf(AwColor.MINT, AwColor.ACCENT)
            ).apply { cornerRadius = dp(18f).toFloat() }
            setOnClickListener { saveAndFinish() }
        }
        col.addView(apply)
        col.addView(awText(
            this, "AirWave 2.2.0 · build 7", 9f, AwColor.DIM
        ).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(12f), 0, 0)
        })

        rebuildSaved()
    }

    private fun field(hint: String, value: String, inputType: Int): EditText =
        EditText(this).apply {
            this.hint = hint
            setText(value)
            textSize = 14f
            setTextColor(AwColor.TEXT)
            setHintTextColor(AwColor.DIM)
            setSingleLine(true)
            this.inputType = inputType
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(12f).toFloat()
                setColor(Color.argb(170, 6, 14, 27))
                setStroke(dp(1f), AwColor.BORDER)
            }
            setPadding(dp(12f), dp(10f), dp(12f), dp(10f))
        }

    private fun fieldParams(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(8f), 0, 0) }

    private fun saveEndpointOnly() {
        val host = ipField.text.toString().trim()
        val port = portField.text.toString().toIntOrNull() ?: 0
        if (host.isEmpty() || port !in 1024..65535) {
            showError("请填写正确的 IP 和 1024–65535 端口")
            return
        }
        Prefs.host = host
        Prefs.port = port
        Prefs.saveSaved(Prefs.addSaved(host, port))
        errorText.text = "已保存"
        errorText.setTextColor(AwColor.MINT)
        rebuildSaved()
    }

    private fun rebuildSaved() {
        savedBox.removeAllViews()
        val items = Prefs.saved()
        if (items.isEmpty()) {
            savedBox.addView(awText(
                this,
                "还没有保存的地址；填写后点“保存此地址”。",
                10f, AwColor.DIM
            ).apply { setPadding(0, dp(6f), 0, dp(4f)) })
            return
        }
        items.forEach { item ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp(6f), 0, dp(6f))
            }
            val info = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setOnClickListener {
                    ipField.setText(item.host)
                    portField.setText(item.port.toString())
                    errorText.text = ""
                }
            }
            info.addView(awText(this, item.host, 12.5f, AwColor.TEXT, medium = true, mono = true))
            info.addView(awText(
                this, "端口 ${item.port} · ${relative(item.lastUsed)}", 9f, AwColor.DIM
            ))
            row.addView(info, LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
            ))
            val del = awText(this, "×", 18f, AwColor.DIM, medium = true).apply {
                gravity = Gravity.CENTER
                setPadding(dp(10f), 0, dp(4f), 0)
                setOnClickListener {
                    Prefs.removeSaved(item.id)
                    rebuildSaved()
                }
            }
            row.addView(del)
            savedBox.addView(row)
            savedBox.addView(View(this).apply {
                setBackgroundColor(Color.argb(18, 255, 255, 255))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, dp(1f)
                )
            })
        }
    }

    private fun relative(time: Long): String {
        if (time <= 0) return "之前"
        val diff = (System.currentTimeMillis() - time) / 1000
        return when {
            diff < 60 -> "刚刚"
            diff < 3600 -> "${diff / 60} 分钟前"
            diff < 86400 -> "${diff / 3600} 小时前"
            else -> "${diff / 86400} 天前"
        }
    }

    private fun showError(text: String) {
        errorText.setTextColor(AwColor.RED)
        errorText.text = text
    }

    private fun saveAndFinish() {
        val host = ipField.text.toString().trim()
        val port = portField.text.toString().toIntOrNull() ?: 0
        if (host.isEmpty() || port !in 1024..65535) {
            showError("请填写正确的 IP 和 1024–65535 端口")
            return
        }
        Prefs.host = host
        Prefs.port = port
        Prefs.mode = mode
        Prefs.saveSaved(Prefs.addSaved(host, port))
        setResult(RESULT_OK, Intent().apply {
            putExtra("host", host)
            putExtra("port", port)
            putExtra("mode", mode.key)
        })
        finish()
    }

    private fun space(dpValue: Float): View = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(1, dp(dpValue))
    }
}
