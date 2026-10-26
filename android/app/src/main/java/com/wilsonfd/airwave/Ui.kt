package com.wilsonfd.airwave

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.SweepGradient
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

object AwColor {
    val BG = Color.rgb(5, 10, 22)
    val BG2 = Color.rgb(8, 16, 31)
    val CARD = Color.rgb(11, 20, 36)
    val CARD2 = Color.rgb(8, 17, 31)
    val BORDER = Color.rgb(27, 43, 68)
    val TEXT = Color.rgb(234, 242, 255)
    val MUTED = Color.rgb(142, 163, 192)
    val DIM = Color.rgb(94, 113, 140)
    val ACCENT = Color.rgb(106, 169, 255)
    val VIOLET = Color.rgb(177, 140, 255)
    val MINT = Color.rgb(86, 224, 192)
    val RED = Color.rgb(255, 112, 128)
    val AMBER = Color.rgb(255, 196, 92)
}

fun Context.dp(v: Float): Int = (v * resources.displayMetrics.density).toInt()

fun View.dp(v: Float): Int = context.dp(v)

fun glassDrawable(context: Context, radiusDp: Float = 22f): GradientDrawable =
    GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        intArrayOf(Color.rgb(14, 26, 46), Color.rgb(8, 18, 33))
    ).apply {
        cornerRadius = context.dp(radiusDp).toFloat()
        setStroke(context.dp(1f), AwColor.BORDER)
    }

fun pillDrawable(context: Context, fill: Int, stroke: Int, radiusDp: Float = 20f): GradientDrawable =
    GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = context.dp(radiusDp).toFloat()
        setColor(fill)
        setStroke(context.dp(1f), stroke)
    }

fun typeface(medium: Boolean = false): Typeface =
    Typeface.create(if (medium) "sans-serif-medium" else "sans-serif", Typeface.NORMAL)

fun awText(
    context: Context,
    text: CharSequence,
    sizeSp: Float,
    color: Int = AwColor.TEXT,
    medium: Boolean = false,
    mono: Boolean = false
): TextView = TextView(context).apply {
    this.text = text
    textSize = sizeSp
    setTextColor(color)
    typeface = if (mono) Typeface.MONOSPACE else typeface(medium)
    includeFontPadding = false
}

class AuroraView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var bg: Shader? = null
    private var glowA: Shader? = null
    private var glowB: Shader? = null

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        bg = LinearGradient(
            0f, 0f, 0f, h.toFloat(),
            intArrayOf(Color.rgb(4, 8, 18), Color.rgb(7, 14, 28), Color.rgb(4, 9, 19)),
            null, Shader.TileMode.CLAMP
        )
        glowA = RadialGradient(
            w * 0.92f, h * 0.08f, w * 0.8f,
            intArrayOf(Color.argb(46, 106, 169, 255), Color.argb(0, 106, 169, 255)),
            null, Shader.TileMode.CLAMP
        )
        glowB = RadialGradient(
            w * 0.08f, h * 0.72f, w * 0.75f,
            intArrayOf(Color.argb(34, 177, 140, 255), Color.argb(0, 177, 140, 255)),
            null, Shader.TileMode.CLAMP
        )
    }

    override fun onDraw(canvas: Canvas) {
        paint.shader = bg
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        paint.shader = glowA
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        paint.shader = glowB
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
    }
}

class GlassCard(context: Context) : LinearLayout(context) {
    init {
        orientation = VERTICAL
        setPadding(dp(16f), dp(14f), dp(16f), dp(14f))
        background = glassDrawable(context)
        elevation = dp(2f).toFloat()
    }
}

class OrbView(context: Context) : View(context) {
    var phase: Phase = Phase.IDLE
        set(value) {
            field = value
            invalidate()
        }
    var level: Float = 0f
        set(value) {
            field = value.coerceIn(0f, 1f)
        }
    var onTap: (() -> Unit)? = null

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val rect = RectF()
    private var downX = 0f
    private var downY = 0f

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val radius = minOf(width, height) / 2f - dp(10f)
        val accent = when (phase) {
            Phase.PLAYING -> AwColor.MINT
            Phase.CONNECTING -> AwColor.ACCENT
            Phase.WAITING -> AwColor.AMBER
            Phase.IDLE -> AwColor.MUTED
        }

        paint.style = Paint.Style.FILL
        paint.shader = RadialGradient(
            cx, cy, radius * 1.45f,
            intArrayOf(
                Color.argb(if (phase == Phase.PLAYING) 46 else 26,
                    Color.red(accent), Color.green(accent), Color.blue(accent)),
                Color.argb(0, Color.red(accent), Color.green(accent), Color.blue(accent))
            ), null, Shader.TileMode.CLAMP
        )
        canvas.drawCircle(cx, cy, radius * 1.45f, paint)
        paint.shader = null

        paint.style = Paint.Style.FILL
        paint.color = Color.rgb(8, 17, 31)
        canvas.drawCircle(cx, cy, radius, paint)

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = dp(1.2f).toFloat()
        paint.color = Color.argb(150, 58, 82, 116)
        canvas.drawCircle(cx, cy, radius, paint)

        val now = System.currentTimeMillis() % 6000L
        val spin = now / 6000f * 360f
        rect.set(cx - radius + dp(9f), cy - radius + dp(9f),
            cx + radius - dp(9f), cy + radius - dp(9f))
        paint.strokeWidth = dp(3f).toFloat()
        paint.strokeCap = Paint.Cap.ROUND
        paint.shader = SweepGradient(
            cx, cy,
            intArrayOf(
                Color.TRANSPARENT, accent,
                AwColor.VIOLET, Color.TRANSPARENT
            ),
            floatArrayOf(0f, 0.28f, 0.62f, 1f)
        )
        val sweep = when (phase) {
            Phase.PLAYING -> 270f
            Phase.CONNECTING -> 290f
            Phase.WAITING -> 150f
            Phase.IDLE -> 110f
        }
        canvas.drawArc(rect, spin - 90f, sweep, false, paint)
        paint.shader = null
        paint.strokeCap = Paint.Cap.BUTT

        if (phase == Phase.PLAYING) {
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = dp(1.5f).toFloat()
            paint.color = Color.argb(90, 86, 224, 192)
            val pulse = radius + dp(4f) + level * dp(10f)
            canvas.drawCircle(cx, cy, pulse, paint)
        }

        paint.style = Paint.Style.FILL
        paint.color = if (phase == Phase.IDLE) AwColor.MUTED else accent
        val powerR = radius * 0.20f
        rect.set(cx - powerR, cy - powerR, cx + powerR, cy + powerR)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = dp(4f).toFloat()
        paint.strokeCap = Paint.Cap.ROUND
        canvas.drawArc(rect, -48f, 276f, false, paint)
        canvas.drawLine(cx, cy - powerR * 1.55f, cx, cy - powerR * 0.10f, paint)

        if (!isAttachedToWindow) return
        postInvalidateOnAnimation()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                return true
            }
            MotionEvent.ACTION_UP -> {
                val dx = event.x - downX
                val dy = event.y - downY
                if (dx * dx + dy * dy < dp(28f) * dp(28f)) {
                    performClick()
                }
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        onTap?.invoke()
        return true
    }
}

class ModeBar(context: Context) : LinearLayout(context) {
    var onSelect: ((LatencyMode) -> Unit)? = null
    private val buttons = mutableListOf<TextView>()
    private var selected = LatencyMode.AUTO

    init {
        orientation = HORIZONTAL
        for (mode in LatencyMode.entries) {
            val tv = awText(context, mode.chip, 10.5f, AwColor.MUTED, medium = true).apply {
                gravity = Gravity.CENTER
                setPadding(0, dp(8f), 0, dp(8f))
                isClickable = true
                setOnClickListener {
                    selected = mode
                    paintButtons()
                    onSelect?.invoke(mode)
                }
            }
            val lp = LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f)
            lp.setMargins(dp(2f), 0, dp(2f), 0)
            addView(tv, lp)
            buttons.add(tv)
        }
        paintButtons()
    }

    fun setSelected(mode: LatencyMode) {
        selected = mode
        paintButtons()
    }

    private fun paintButtons() {
        buttons.forEachIndexed { i, tv ->
            val mode = LatencyMode.entries[i]
            if (mode == selected) {
                tv.background = pillDrawable(
                    context, Color.argb(235, 234, 242, 255), AwColor.TEXT, 18f
                )
                tv.setTextColor(AwColor.BG)
            } else {
                tv.background = pillDrawable(
                    context, Color.argb(18, 255, 255, 255), AwColor.BORDER, 18f
                )
                tv.setTextColor(AwColor.MUTED)
            }
        }
    }
}

class StatCard(context: Context, title: String, value: String, sub: String) : LinearLayout(context) {
    private val valueView: TextView
    private val subView: TextView

    init {
        orientation = VERTICAL
        setPadding(dp(12f), dp(10f), dp(12f), dp(10f))
        background = glassDrawable(context, 16f)
        addView(awText(context, title, 9f, AwColor.DIM, medium = true))
        valueView = awText(context, value, 17f, AwColor.TEXT, medium = true, mono = true)
        valueView.setPadding(0, dp(2f), 0, 0)
        addView(valueView)
        subView = awText(context, sub, 8.5f, AwColor.DIM)
        subView.setPadding(0, dp(1f), 0, 0)
        addView(subView)
    }

    fun update(value: String, sub: String? = null) {
        valueView.text = value
        if (sub != null) subView.text = sub
    }
}
