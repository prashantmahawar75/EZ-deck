"""
renderers/content_renderer.py — Renders text-based slide content.

Handles title slides, bullets, exec summaries, stat highlights, callouts,
section dividers, and key takeaways using python-pptx text frames.
"""

from __future__ import annotations

import logging
from typing import Any

from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

from config import (
    SLIDE_WIDTH_INCHES,
    SLIDE_HEIGHT_INCHES,
    MARGIN_LEFT_FRAC,
    MARGIN_RIGHT_FRAC,
    MARGIN_TOP_FRAC,
    TITLE_TOP_FRAC,
    TITLE_HEIGHT_FRAC,
    CONTENT_TOP_FRAC,
    CONTENT_HEIGHT_FRAC,
    FONT_SIZE_TITLE,
    FONT_SIZE_SECTION_HEADER,
    FONT_SIZE_BODY,
    FONT_SIZE_SMALL,
    FONT_SIZE_FOOTNOTE,
    FONT_SIZE_STAT_NUMBER,
    FONT_SIZE_STAT_LABEL,
    FONT_SIZE_STAT_CONTEXT,
    MAX_BULLETS_PER_SLIDE,
    MAX_STATS_PER_SLIDE,
    MAX_TAKEAWAYS,
)

logger = logging.getLogger(__name__)


def _safe_icon_text(icon_hint: Any) -> str:
    text = str(icon_hint or "").strip()
    if not text:
        return "+"

    fallback_map = {
        "✓": "+",
        "✔": "+",
        "✦": "*",
        "★": "*",
        "⚡": "!",
        "⚠": "!",
        "📈": "^",
        "📉": "v",
        "→": ">",
    }
    if text in fallback_map:
        return fallback_map[text]
    if all(ord(ch) < 128 for ch in text):
        return text[:1]
    for source, fallback in fallback_map.items():
        if source in text:
            return fallback
    return "+"


def _dims() -> dict[str, float]:
    """Compute layout dimensions from config fractions.

    Returns:
        Dict with sw, sh, lm, rm, usable_w, title_top, title_h, content_top, content_h.
    """
    sw = SLIDE_WIDTH_INCHES
    sh = SLIDE_HEIGHT_INCHES
    lm = sw * MARGIN_LEFT_FRAC
    rm = sw * MARGIN_RIGHT_FRAC
    return {
        "sw": sw, "sh": sh,
        "lm": lm, "rm": rm,
        "usable_w": sw - lm - rm,
        "title_top": sh * TITLE_TOP_FRAC,
        "title_h": sh * TITLE_HEIGHT_FRAC,
        "content_top": sh * CONTENT_TOP_FRAC,
        "content_h": sh * CONTENT_HEIGHT_FRAC,
    }


def render_title_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render a TITLE slide.

    Args:
        content: Dict with "headline", "subheadline", "presenter".
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()

    # Always use manual layout for consistent visual styling
    headline = content.get("headline", "")
    subheadline = content.get("subheadline", "")

    # Dark background strip (lower 60% of slide)
    bg_rect = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0),
        Inches(d["sw"]), Inches(d["sh"]),
    )
    bg_rect.fill.solid()
    bg_rect.fill.fore_color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    bg_rect.line.fill.background()
    # Send background to back
    sp = bg_rect._element
    sp.getparent().insert(0, sp)

    # Left accent bar
    accent_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(d["lm"]), Inches(d["sh"] * 0.28),
        Inches(0.08), Inches(d["sh"] * 0.35),
    )
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = accent
    accent_bar.line.fill.background()

    # Headline — big, white, left-aligned next to accent bar
    txbox = slide.shapes.add_textbox(
        Inches(d["lm"] + 0.3),
        Inches(d["sh"] * 0.25),
        Inches(d["usable_w"] - 0.5),
        Inches(d["sh"] * 0.3),
    )
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = headline
    run.font.size = Pt(44)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    run.font.name = font_name

    # Subheadline — lighter, smaller, with proper text box sizing to avoid truncation
    if subheadline:
        txbox2 = slide.shapes.add_textbox(
            Inches(d["lm"] + 0.3),
            Inches(d["sh"] * 0.58),
            Inches(d["usable_w"] * 0.9),  # BUG FIX: Increased from 0.7 to 0.9 for full subtitle
            Inches(d["sh"] * 0.22),  # BUG FIX: Increased from 0.12 to 0.22 for multi-line subtitles
        )
        tf2 = txbox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.LEFT
        run2 = p2.add_run()
        run2.text = subheadline
        run2.font.size = Pt(20)
        run2.font.color.rgb = RGBColor(0xAA, 0xBB, 0xCC)
        run2.font.name = font_name

    logger.debug("Rendered title slide: %s", headline)


def render_agenda_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render an AGENDA slide with numbered items.

    Args:
        content: Dict with "items" (list of {number, topic}).
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()
    items = content.get("items", [])

    if not items:
        return

    item_height = min(0.65, d["content_h"] / len(items))
    start_x = d["lm"] + 0.2
    start_y = d["content_top"] + 0.2

    for i, item in enumerate(items):
        iy = start_y + i * item_height

        # Number circle - slightly larger for 2-digit numbers
        item_number = item.get("number", i + 1)
        circle_size = 0.48 if item_number >= 10 else 0.42
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(start_x),
            Inches(iy),
            Inches(circle_size),
            Inches(circle_size),
        )
        circle.fill.solid()
        circle.fill.fore_color.rgb = accent
        circle.line.fill.background()

        tf = circle.text_frame
        tf.auto_size = None  # Prevent auto-sizing
        tf.word_wrap = False  # CRITICAL: Prevent text wrapping for 2-digit numbers
        # Vertical centering within circle
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        run = p.add_run()
        run.text = str(item_number)
        # BUG 10 FIX: Font size for badges - keep readable for 2-digits
        badge_font_size = 12 if item_number >= 10 else 14
        run.font.size = Pt(badge_font_size)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.name = font_name

        # Topic text
        txbox = slide.shapes.add_textbox(
            Inches(start_x + circle_size + 0.3),
            Inches(iy),
            Inches(d["usable_w"] - circle_size - 0.7),
            Inches(circle_size),
        )
        tf = txbox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = item.get("topic", "")
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        run.font.name = font_name

    logger.debug("Rendered agenda with %d items", len(items))


def render_exec_summary_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render an EXEC_SUMMARY slide.

    Args:
        content: Dict with "insights" and optional "key_metric".
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()
    insights = content.get("insights", [])[:4]
    key_metric = content.get("key_metric")

    if not insights and not key_metric:
        return

    # ── KEY METRIC: BIG NUMBER at top-left for visual hierarchy ──
    # BUG 1 FIX: Ensure proper vertical spacing and remove overlapping label
    if key_metric:
        metric_str = str(key_metric)
        metric_top = d["content_top"]
        
        # Dynamically size based on text length to prevent overlap
        # Short metrics (numbers like "72" or "$1.2M") get big font + small area
        # Long metrics (sentences) get smaller font + larger area
        is_long_metric = len(metric_str) > 25
        
        if is_long_metric:
            metric_font_size = 36  # Smaller font for long text
            metric_height = 2.2  # More height for wrapping
        else:
            metric_font_size = 52  # Big font for short numbers
            metric_height = 1.4  # Less height needed
        
        metric_box = slide.shapes.add_textbox(
            Inches(d["lm"] + 0.3),
            Inches(metric_top),
            Inches(d["usable_w"] * 0.85),  # Wider box to reduce wrapping
            Inches(metric_height),
        )
        tf = metric_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = metric_str
        run.font.size = Pt(metric_font_size)
        run.font.bold = True
        run.font.color.rgb = accent
        run.font.name = font_name

        # NOTE: Removed "KEY METRIC" label to avoid overlap and visual clutter

        # Accent underline below metric
        line = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(d["lm"] + 0.3),
            Inches(metric_top + metric_height + 0.1),
            Inches(d["usable_w"] * 0.4),
            Inches(0.04),
        )
        line.fill.solid()
        line.fill.fore_color.rgb = accent
        line.line.fill.background()

        # CRITICAL: Insights start BELOW metric area with clear separation
        insight_top = metric_top + metric_height + 0.4
    else:
        insight_top = d["content_top"] + 0.2

    # ── INSIGHTS: styled cards with accent left-border ──
    if insights:
        card_height = min(0.75, (d["sh"] - insight_top - 0.5) / len(insights))
        for i, insight in enumerate(insights):
            iy = insight_top + i * card_height

            # Left accent bar per insight
            bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(d["lm"] + 0.3),
                Inches(iy + 0.05),
                Inches(0.06),
                Inches(card_height - 0.15),
            )
            bar.fill.solid()
            bar.fill.fore_color.rgb = accent
            bar.line.fill.background()

            # Insight text
            txbox = slide.shapes.add_textbox(
                Inches(d["lm"] + 0.6),
                Inches(iy),
                Inches(d["usable_w"] - 1.0),
                Inches(card_height),
            )
            tf = txbox.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            run = p.add_run()
            run.text = insight
            run.font.size = Pt(FONT_SIZE_BODY)
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            run.font.name = font_name

    logger.debug("Rendered exec summary with %d insights", len(insights))


def render_bullets_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render a CONTENT_BULLETS slide.

    Args:
        content: Dict with "bullets" (list of {text, sub_bullets}).
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()
    bullets = content.get("bullets", [])[:MAX_BULLETS_PER_SLIDE]

    if not bullets:
        return

    # Left accent bar — full height visual anchor
    accent_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(d["lm"] + 0.2),
        Inches(d["content_top"]),
        Inches(0.07),
        Inches(d["content_h"]),
    )
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = accent
    accent_bar.line.fill.background()

    # Render each bullet as an independent row with hierarchy
    n = len(bullets)
    row_h = min(0.85, d["content_h"] / n)

    for i, bullet in enumerate(bullets):
        iy = d["content_top"] + i * row_h
        text = bullet.get("text", "") if isinstance(bullet, dict) else str(bullet)

        # Main bullet text — bold accent marker + text
        txbox = slide.shapes.add_textbox(
            Inches(d["lm"] + 0.55),
            Inches(iy + 0.05),
            Inches(d["usable_w"] - 1.0),
            Inches(0.45),
        )
        tf = txbox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT

        marker = p.add_run()
        marker.text = "▸ "
        marker.font.size = Pt(FONT_SIZE_BODY + 2)
        marker.font.bold = True
        marker.font.color.rgb = accent
        marker.font.name = font_name

        run = p.add_run()
        run.text = text
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0x2A, 0x2A, 0x2A)
        run.font.name = font_name

        # Sub-bullets — lighter, indented
        sub_bullets = bullet.get("sub_bullets") if isinstance(bullet, dict) else None
        if sub_bullets:
            sub_box = slide.shapes.add_textbox(
                Inches(d["lm"] + 0.9),
                Inches(iy + 0.45),
                Inches(d["usable_w"] - 1.4),
                Inches(row_h - 0.5),
            )
            stf = sub_box.text_frame
            stf.word_wrap = True
            for j, sb in enumerate(sub_bullets[:3]):
                p_sub = stf.paragraphs[0] if j == 0 else stf.add_paragraph()
                p_sub.space_before = Pt(2)
                run_sub = p_sub.add_run()
                run_sub.text = f"– {sb}"
                run_sub.font.size = Pt(FONT_SIZE_SMALL)
                run_sub.font.color.rgb = RGBColor(0x77, 0x77, 0x77)
                run_sub.font.name = font_name

    logger.debug("Rendered bullet slide with %d bullets", len(bullets))


def render_two_column_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render a CONTENT_TWO_COLUMN slide.

    Args:
        content: Dict with "left" and "right" column dicts.
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()

    left_data = content.get("left", {})
    right_data = content.get("right", {})

    col_width = (d["usable_w"] - 0.6) / 2  # 0.6 inch gap

    for col_idx, col_data in enumerate([left_data, right_data]):
        x = d["lm"] + col_idx * (col_width + 0.6)
        heading = col_data.get("heading", "")
        points = col_data.get("points", [])

        # Column heading
        heading_box = slide.shapes.add_textbox(
            Inches(x),
            Inches(d["content_top"]),
            Inches(col_width),
            Inches(0.5),
        )
        tf = heading_box.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = heading
        run.font.size = Pt(20)
        run.font.bold = True
        run.font.color.rgb = accent
        run.font.name = font_name

        # Divider line under heading
        line = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(x),
            Inches(d["content_top"] + 0.55),
            Inches(col_width),
            Inches(0.03),
        )
        line.fill.solid()
        line.fill.fore_color.rgb = accent
        line.line.fill.background()

        # Points
        points_box = slide.shapes.add_textbox(
            Inches(x),
            Inches(d["content_top"] + 0.7),
            Inches(col_width),
            Inches(d["content_h"] - 0.8),
        )
        tf = points_box.text_frame
        tf.word_wrap = True

        for i, point in enumerate(points[:MAX_BULLETS_PER_SLIDE]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_before = Pt(6)
            run = p.add_run()
            run.text = f"• {point}"
            run.font.size = Pt(FONT_SIZE_SMALL)
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            run.font.name = font_name

    logger.debug("Rendered two-column slide")


def render_stat_highlight_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render a STAT_HIGHLIGHT slide with large numbers and labels.

    Args:
        content: Dict with "stats" (list of {value, label, context}).
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()
    stats = content.get("stats", [])[:MAX_STATS_PER_SLIDE]

    if not stats:
        return

    # Card palette for visual variety
    card_colors = [
        RGBColor(0x2E, 0x86, 0xAB),  # blue
        RGBColor(0xA2, 0x3B, 0x72),  # magenta
        RGBColor(0xF1, 0x8F, 0x01),  # orange
        RGBColor(0x44, 0xBB, 0xA4),  # teal
    ]

    n = len(stats)
    gap = 0.3
    total_gap = gap * (n - 1) if n > 1 else 0
    card_w = (d["usable_w"] - 0.4 - total_gap) / n
    card_h = d["content_h"] * 0.85
    card_top = d["content_top"] + 0.1

    for i, stat in enumerate(stats):
        sx = d["lm"] + 0.2 + i * (card_w + gap)
        card_color = card_colors[i % len(card_colors)]

        # Background card with rounded corners
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(sx),
            Inches(card_top),
            Inches(card_w),
            Inches(card_h),
        )
        card.fill.solid()
        # Light tint of the card color (mix with white)
        r = min(255, card_color[0] + (255 - card_color[0]) * 85 // 100)
        g = min(255, card_color[1] + (255 - card_color[1]) * 85 // 100)
        b = min(255, card_color[2] + (255 - card_color[2]) * 85 // 100)
        card.fill.fore_color.rgb = RGBColor(r, g, b)
        card.line.fill.background()

        # Top accent stripe on card
        stripe = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(sx),
            Inches(card_top),
            Inches(card_w),
            Inches(0.06),
        )
        stripe.fill.solid()
        stripe.fill.fore_color.rgb = card_color
        stripe.line.fill.background()

        # BIG NUMBER — hero element (auto-scale for text values)
        value_text = str(stat.get("value", ""))
        if len(value_text) <= 6:
            stat_font = Pt(FONT_SIZE_STAT_NUMBER)  # 60pt for short numbers
        elif len(value_text) <= 12:
            stat_font = Pt(36)
        else:
            stat_font = Pt(24)

        num_box = slide.shapes.add_textbox(
            Inches(sx + 0.15),
            Inches(card_top + 0.3),
            Inches(card_w - 0.3),
            Inches(1.4),
        )
        tf = num_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = value_text
        run.font.size = stat_font
        run.font.bold = True
        run.font.color.rgb = card_color
        run.font.name = font_name

        # Label — supporting text
        label_box = slide.shapes.add_textbox(
            Inches(sx + 0.15),
            Inches(card_top + 1.7),
            Inches(card_w - 0.3),
            Inches(0.6),
        )
        tf = label_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = stat.get("label", "").upper()
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        run.font.name = font_name

        # Context — smallest, lightest
        context = stat.get("context", "")
        if context:
            ctx_box = slide.shapes.add_textbox(
                Inches(sx + 0.15),
                Inches(card_top + 2.25),
                Inches(card_w - 0.3),
                Inches(0.6),
            )
            tf = ctx_box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            run = p.add_run()
            run.text = context
            run.font.size = Pt(FONT_SIZE_STAT_CONTEXT)
            run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            run.font.name = font_name

    logger.debug("Rendered stat highlight with %d stats", len(stats))


def render_key_takeaways_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render a KEY_TAKEAWAYS slide.

    Args:
        content: Dict with "takeaways" (list of {icon_hint, text}).
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()
    takeaways = content.get("takeaways", [])[:MAX_TAKEAWAYS]

    if not takeaways:
        return

    n = len(takeaways)
    card_height = min(0.9, (d["content_h"] - 0.2) / n)
    start_y = d["content_top"] + 0.1

    for i, ta in enumerate(takeaways):
        iy = start_y + i * card_height

        # Card background — light gray
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(d["lm"] + 0.3),
            Inches(iy + 0.05),
            Inches(d["usable_w"] - 0.6),
            Inches(card_height - 0.12),
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xF5, 0xF7, 0xFA)
        card.line.fill.background()

        # Left accent border on card
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(d["lm"] + 0.3),
            Inches(iy + 0.05),
            Inches(0.07),
            Inches(card_height - 0.12),
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()

        # Icon circle
        circle_size = 0.35
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(d["lm"] + 0.6),
            Inches(iy + (card_height - circle_size) / 2),
            Inches(circle_size),
            Inches(circle_size),
        )
        circle.fill.solid()
        circle.fill.fore_color.rgb = accent
        circle.line.fill.background()

        tf = circle.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = _safe_icon_text(ta.get("icon_hint", "+"))
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.name = font_name

        # Takeaway text — vertically centered in card
        txbox = slide.shapes.add_textbox(
            Inches(d["lm"] + 1.15),
            Inches(iy + 0.08),
            Inches(d["usable_w"] - 1.7),
            Inches(card_height - 0.16),
        )
        tf = txbox.text_frame
        tf.word_wrap = True
        tf.auto_size = None
        try:
            tf.paragraphs[0].space_before = Pt(0)
        except Exception:
            pass
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = ta.get("text", "")
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0x2A, 0x2A, 0x2A)
        run.font.name = font_name

    logger.debug("Rendered key takeaways with %d items", len(takeaways))


def render_section_divider_slide(
    content: dict[str, Any],
    slide: Any,
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> None:
    """Render a SECTION_DIVIDER slide.

    Args:
        content: Dict with "section_number", "section_title", "section_subtitle".
        slide: python-pptx slide object.
        accent_color: Theme accent color.
        font_name: Font family.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    d = _dims()

    section_title = content.get("section_title", "")
    section_subtitle = content.get("section_subtitle", "")
    section_number = content.get("section_number", "")

    # Always use manual layout (placeholders don't render reliably)

    # Dark background — full slide
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0),
        Inches(d["sw"]), Inches(d["sh"]),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    bg.line.fill.background()
    sp = bg._element
    sp.getparent().insert(0, sp)

    # Section number — small, uppercase, accent color
    if section_number:
        num_box = slide.shapes.add_textbox(
            Inches(d["lm"]),
            Inches(d["sh"] * 0.28),
            Inches(d["usable_w"]),
            Inches(0.5),
        )
        tf = num_box.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = f"SECTION {section_number}"
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = accent
        run.font.name = font_name

    # Accent line — short, centered
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(d["sw"] / 2 - 0.6),
        Inches(d["sh"] * 0.38),
        Inches(1.2),
        Inches(0.05),
    )
    line.fill.solid()
    line.fill.fore_color.rgb = accent
    line.line.fill.background()

    # Title — large, white, centered
    title_box = slide.shapes.add_textbox(
        Inches(d["lm"]),
        Inches(d["sh"] * 0.42),
        Inches(d["usable_w"]),
        Inches(1.2),
    )
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = section_title
    run.font.size = Pt(FONT_SIZE_SECTION_HEADER)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    run.font.name = font_name

    # Subtitle — softer, lighter
    if section_subtitle:
        sub_box = slide.shapes.add_textbox(
            Inches(d["lm"] + d["usable_w"] * 0.1),
            Inches(d["sh"] * 0.58),
            Inches(d["usable_w"] * 0.8),
            Inches(0.6),
        )
        tf = sub_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = section_subtitle
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0xAA, 0xBB, 0xCC)
        run.font.name = font_name

    logger.debug("Rendered section divider: %s", section_title)
