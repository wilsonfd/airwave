package com.wilsonfd.airwave

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Outline
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewOutlineProvider
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity(), CoreListener {

    private lateinit var orb: OrbView
    private lateinit var status: TextView
    private lateinit var sub: TextView
    private lateinit var address: TextView
    private lateinit var modeBar: ModeBar
    private lateinit var modeHint: TextView
    private lateinit var bufferCard: StatCard
    private lateinit var lossCard: StatCard
    private lateinit var underCard: StatCard
    private lateinit var recvCard: StatCard
    private lateinit var settingsButton: TextView

    private var host = ""
    private var port = 13666

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AirwaveCore.init(applicationContext)
        host = Prefs.host
        port = Prefs.port

        window.statusBarColor = AwColor.BG
        window.navigationBarColor = AwColor.BG
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)

        buildUi()
        AirwaveCore.addListener(this)
        requestNotificationPermission()
    }

    override fun onResume() {
        super.onResume()
        host = Prefs.host
        port = Prefs.port
        render(AirwaveCore.currentState(), AirwaveCore.currentStats())
    }

    override fun onDestroy() {
        AirwaveCore.removeListener(this)
        super.onDestroy()
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
            setPadding(dp(20f), dp(26f), dp(20f), dp(34f))
        }
        scroll.addView(col, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT
        ))
        root.addView(scroll, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT
        ))
        setContentView(root)

        col.addView(buildHeader())
        col.addView(space(10f))

        orb = OrbView(this)
        orb.onTap = { onOrbTap() }
        col.addView(orb, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(238f)
        ))

        status = awText(this, "点上方圆钮开始连接", 20f, AwColor.TEXT, medium = true).apply {
            gravity = Gravity.CENTER
        }
        col.addView(status)
        sub = awText(this, "同一 WiFi · 5 GHz · PC 先点开始推流", 10.5f, AwColor.MUTED).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(5f), 0, 0)
        }
        col.addView(sub)

        col.addView(space(18f))

        val modeHead = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        modeHead.addView(awText(this, "延迟模式", 12f, AwColor.TEXT, medium = true), LinearLayout.LayoutParams(
            0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
        ))
        modeHint = awText(this, "实时切换", 9.5f, AwColor.DIM)
        modeHead.addView(modeHint)
        col.addView(modeHead)
        col.addView(space(7f))

        modeBar = ModeBar(this).apply {
            onSelect = { mode ->
                AirwaveCore.setMode(mode)
                modeHint.text = mode.subtitle
                modeHint.setTextColor(AwColor.MUTED)
                val st = AirwaveCore.currentState()
                bufferCard.update("${if (st.phase == Phase.PLAYING) "—" else "—"} ms", "目标 ${mode.prebufferMs} ms")
            }
        }
        col.addView(modeBar)
        modeBar.setSelected(AirwaveCore.currentMode())
        modeHint.text = AirwaveCore.currentMode().subtitle
        modeHint.setTextColor(AwColor.MUTED)

        col.addView(space(14f))

        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        bufferCard = StatCard(this, "缓冲", "— ms", "目标 ${AirwaveCore.currentMode().prebufferMs} ms")
        lossCard = StatCard(this, "丢包", "0.0%", "时钟校正 0")
        row1.addView(bufferCard, statParams())
        row1.addView(lossCard, statParams())
        col.addView(row1)

        val row2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(8f), 0, 0)
        }
        underCard = StatCard(this, "欠载", "0", "次")
        recvCard = StatCard(this, "已接收", "0", "包")
        row2.addView(underCard, statParams())
        row2.addView(recvCard, statParams())
        col.addView(row2)

        col.addView(space(14f))

        val card = GlassCard(this)
        val cardHead = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        cardHead.addView(awText(this, "电脑连接", 10f, AwColor.DIM, medium = true), LinearLayout.LayoutParams(
            0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
        ))
        settingsButton = awText(this, "修改", 10f, AwColor.ACCENT, medium = true).apply {
            setPadding(dp(10f), dp(5f), dp(10f), dp(5f))
            background = pillDrawable(
                this@MainActivity,
                Color.argb(28, 106, 169, 255), Color.argb(70, 106, 169, 255), 14f
            )
            setOnClickListener { openSettings() }
        }
        cardHead.addView(settingsButton)
        card.addView(cardHead)

        address = awText(this, "未设置", 13f, AwColor.TEXT, medium = true, mono = true).apply {
            setPadding(0, dp(7f), 0, 0)
        }
        card.addView(address)

        val portHint = awText(this, "UDP 13666 · 与电脑同一局域网", 9.5f, AwColor.DIM).apply {
            setPadding(0, dp(3f), 0, 0)
        }
        card.addView(portHint)
        col.addView(card)

        col.addView(space(12f))

        val help = awText(
            this,
            "5 GHz 优先 · PC 用网线接路由更稳 · 7ms 包最适合低延迟",
            9.5f,
            AwColor.DIM
        ).apply {
            gravity = Gravity.CENTER
        }
        col.addView(help)

        val footer = awText(
            this,
            "AirWave 2.2.0 · build 7   ·   仅局域网   ·   只传音频",
            8.5f,
            AwColor.DIM
        ).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(14f), 0, 0)
        }
        col.addView(footer)

        render(AirwaveCore.currentState(), AirwaveCore.currentStats())
    }

    private fun buildHeader(): LinearLayout {
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val logo = ImageView(this).apply {
            setImageResource(R.mipmap.ic_launcher)
            scaleType = ImageView.ScaleType.CENTER_CROP
            clipToOutline = true
            outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(view: View, outline: Outline) {
                    outline.setRoundRect(
                        0, 0, view.width, view.height,
                        this@MainActivity.dp(11f).toFloat()
                    )
                }
            }
        }
        header.addView(logo, LinearLayout.LayoutParams(dp(40f), dp(40f)))

        val titles = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10f), 0, 0, 0)
        }
        titles.addView(awText(this, "AirWave", 21f, AwColor.TEXT, medium = true))
        titles.addView(awText(this, "局域网无损音频 · v2.2.0", 10.5f, AwColor.MUTED))
        header.addView(titles, LinearLayout.LayoutParams(
            0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f
        ))

        val gear = awText(this, "设置", 10.5f, AwColor.TEXT, medium = true).apply {
            setPadding(dp(13f), dp(8f), dp(13f), dp(8f))
            background = pillDrawable(
                this@MainActivity,
                Color.argb(22, 255, 255, 255), AwColor.BORDER, 18f
            )
            setOnClickListener { openSettings() }
        }
        header.addView(gear)
        return header
    }

    private fun statParams(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
            setMargins(dp(4f), 0, dp(4f), 0)
        }

    private fun space(dpValue: Float): View = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(1, dp(dpValue))
    }

    private fun onOrbTap() {
        if (AirwaveCore.isActive()) {
            AirwaveCore.disconnect()
            stopService(Intent(this, StreamService::class.java))
        } else if (host.isBlank()) {
            openSettings()
        } else {
            startStream()
        }
    }

    private fun startStream() {
        val i = Intent(this, StreamService::class.java).setAction(StreamService.ACTION_START)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
        AirwaveCore.connect(host, port, AirwaveCore.currentMode())
    }

    private fun openSettings() {
        startActivityForResult(Intent(this, SettingsActivity::class.java), 42)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 42) return
        if (resultCode == Activity.RESULT_OK && data != null) {
            val newHost = data.getStringExtra("host") ?: return
            val newPort = data.getIntExtra("port", 13666)
            val mode = LatencyMode.fromKey(data.getStringExtra("mode"))
            val wasActive = AirwaveCore.isActive()
            host = newHost
            port = newPort
            if (wasActive) {
                AirwaveCore.disconnect()
                modeBar.setSelected(mode)
                startStream()
            } else {
                modeBar.setSelected(mode)
            }
            render(AirwaveCore.currentState(), AirwaveCore.currentStats())
        }
    }

    override fun onCoreState(state: CoreState) {
        runOnUiThread { render(state, AirwaveCore.currentStats()) }
    }

    override fun onCoreStats(stats: CoreStats) {
        runOnUiThread {
            bufferCard.update("${stats.bufferMs} ms", "延迟约 ${stats.latencyMs} ms")
            lossCard.update(String.format("%.1f%%", stats.lossPercent), "校正 ${stats.trimmed}")
            underCard.update("${stats.underruns}", "次")
            recvCard.update("${stats.received}", "包")
            orb.level = stats.level
        }
    }

    private fun render(state: CoreState, stats: CoreStats) {
        host = state.host.ifBlank { host }
        port = if (state.port > 0) state.port else port
        status.text = state.status
        orb.phase = state.phase
        address.text = if (host.isBlank()) "未设置" else "$host:$port"
        modeBar.setSelected(state.mode)
        modeHint.text = state.mode.subtitle
        modeHint.setTextColor(AwColor.MUTED)
        sub.text = when (state.phase) {
            Phase.IDLE -> "同一 WiFi · 5 GHz · PC 先点开始推流"
            Phase.CONNECTING -> "正在建立 UDP 连接…"
            Phase.WAITING -> if (state.format.isBlank()) "已连接，等待电脑播放声音" else state.format
            Phase.PLAYING -> if (state.format.isBlank()) "正在播放" else "正在播放 · ${state.format}"
        }
        bufferCard.update("${stats.bufferMs} ms", "延迟约 ${stats.latencyMs} ms")
        lossCard.update(String.format("%.1f%%", stats.lossPercent), "校正 ${stats.trimmed}")
        underCard.update("${stats.underruns}", "次")
        recvCard.update("${stats.received}", "包")
        orb.level = stats.level
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7)
        }
    }
}
