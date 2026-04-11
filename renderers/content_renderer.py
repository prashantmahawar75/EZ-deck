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

    # Try to use the layout's placeholders first
    used_placeholders = False
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:  # Title
            ph.text = content.get("headline", "")
            for p in ph.text_frame.paragraphs:
                for run in p.runs:
                    run.font.name = font_name
            used_placeholders = True
        elif ph.placeholder_format.idx == 1:  # Subtitle
            subheadline = content.get("subheadline", "")
            presenter = content.get("presenter", "")
            ph.text = subheadline
            if presenter:
                p = ph.text_frame.add_paragraph()
                run = p.add_run()
                run.text = f"\n{presenter}"
                run.font.size = Pt(FONT_SIZE_SMALL)
                run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                run.font.name = font_name
            for p in ph.text_frame.paragraphs:
                for run in p.runs:
                    run.font.name = font_name
            used_placeholders = True

    if used_placeholders:
        return

    # Fallback: create text boxes manually
    headline = content.get("headline", "")
    subheadline = content.get("subheadline", "")

    # Headline - centered vertically
    txbox = slide.shapes.add_textbox(
        Inches(d["lm"]),
        Inches(d["sh"] * 0.3),
        Inches(d["usable_w"]),
        Inches(d["sh"] * 0.25),
    )
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = headline
    run.font.size = Pt(FONT_SIZE_SECTION_HEADER)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    run.font.name = font_name

    # Subheadline
    if subheadline:
        txbox2 = slide.shapes.add_textbox(
            Inches(d["lm"] + d["usable_w"] * 0.1),
            Inches(d["sh"] * 0.55),
            Inches(d["usable_w"] * 0.8),
            Inches(d["sh"] * 0.15),
        )
        tf2 = txbox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.CENTER
        run2 = p2.add_run()
        run2.text = subheadline
        run2.font.size = Pt(FONT_SIZE_BODY)
        run2.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        run2.font.name = font_name

    # Accent line
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(d["sw"] / 2 - 1.5),
        Inches(d["sh"] * 0.52),
        Inches(3),
        Inches(0.04),
    )
    line.fill.solid()
    line.fill.fore_color.rgb = accent
    line.line.fill.background()

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

        # Number circle
        circle_size = 0.42
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
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(item.get("number", i + 1))
        run.font.size = Pt(14)
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

    if not insights:
        return

    # Insights as styled bullets
    txbox = slide.shapes.add_textbox(
        Inches(d["lm"] + 0.3),
        Inches(d["content_top"]),
        Inches(d["usable_w"] - 0.6),
        Inches(d["content_h"] * 0.7),
    )
    tf = txbox.text_frame
    tf.word_wrap = True

    for i, insight in enumerate(insights):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(8)
        p.space_after = Pt(8)
        p.level = 0

        # Bullet marker
        run_bullet = p.add_run()
        run_bullet.text = "▸ "
        run_bullet.font.size = Pt(FONT_SIZE_BODY)
        run_bullet.font.color.rgb = accent
        run_bullet.font.name = font_name

        run_text = p.add_run()
        run_text.text = insight
        run_text.font.size = Pt(FONT_SIZE_BODY)
        run_text.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        run_text.font.name = font_name

    # Key metric callout
    if key_metric:
        metric_top = d["content_top"] + d["content_h"] * 0.75
        metric_box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(d["lm"] + d["usable_w"] * 0.2),
            Inches(metric_top),
            Inches(d["usable_w"] * 0.6),
            Inches(0.7),
        )
        metric_box.fill.solid()
        metric_box.fill.fore_color.rgb = accent
        metric_box.line.fill.background()

        tf = metric_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = f"Key Metric: {key_metric}"
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
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

    # Try to use content placeholder
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 1:  # Content placeholder
            tf = ph.text_frame
            tf.clear()
            for i, bullet in enumerate(bullets):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.level = 0
                p.space_before = Pt(6)
                p.line_spacing = 1.3
                run = p.add_run()
                text = bullet.get("text", "") if isinstance(bullet, dict) else str(bullet)
                run.text = f"• {text}"
                run.font.size = Pt(FONT_SIZE_BODY)
                run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
                run.font.name = font_name

                # Sub-bullets
                sub_bullets = bullet.get("sub_bullets") if isinstance(bullet, dict) else None
                if sub_bullets:
                    for sb in sub_bullets[:3]:
                        p_sub = tf.add_paragraph()
                        p_sub.level = 1
                        p_sub.space_before = Pt(2)
                        run_sub = p_sub.add_run()
                        run_sub.text = f"  – {sb}"
                        run_sub.font.size = Pt(FONT_SIZE_SMALL)
                        run_sub.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
                        run_sub.font.name = font_name
            return

    # Fallback: manual text box
    txbox = slide.shapes.add_textbox(
        Inches(d["lm"] + 0.3),
        Inches(d["content_top"]),
        Inches(d["usable_w"] - 0.6),
        Inches(d["content_h"]),
    )
    tf = txbox.text_frame
    tf.word_wrap = True

    for i, bullet in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(8)
        p.space_after = Pt(4)
        p.line_spacing = 1.3

        run = p.add_run()
        text = bullet.get("text", "") if isinstance(bullet, dict) else str(bullet)
        run.text = f"• {text}"
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        run.font.name = font_name

        sub_bullets = bullet.get("sub_bullets") if isinstance(bullet, dict) else None
        if sub_bullets:
            for sb in sub_bullets[:3]:
                p_sub = tf.add_paragraph()
                p_sub.space_before = Pt(2)
                run_sub = p_sub.add_run()
                run_sub.text = f"    – {sb}"
                run_sub.font.size = Pt(FONT_SIZE_SMALL)
                run_sub.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
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

    col_width = (d["usable_w"] - 0.5) / 2  # 0.5 inch gap

    for col_idx, col_data in enumerate([left_data, right_data]):
        x = d["lm"] + col_idx * (col_width + 0.5)
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

    # Thin horizontal rule above stats
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(d["lm"] + d["usable_w"] * 0.1),
        Inches(d["content_top"]),
        Inches(d["usable_w"] * 0.8),
        Inches(0.03),
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = accent
    rule.line.fill.background()

    # Stats layout
    n = len(stats)
    stat_width = d["usable_w"] / n
    stat_top = d["content_top"] + 0.4

    for i, stat in enumerate(stats):
        sx = d["lm"] + i * stat_width

        # Large number
        num_box = slide.shapes.add_textbox(
            Inches(sx),
            Inches(stat_top),
            Inches(stat_width),
            Inches(1.2),
        )
        tf = num_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(stat.get("value", ""))
        run.font.size = Pt(FONT_SIZE_STAT_NUMBER)
        run.font.bold = True
        run.font.color.rgb = accent
        run.font.name = font_name

        # Label
        label_box = slide.shapes.add_textbox(
            Inches(sx),
            Inches(stat_top + 1.3),
            Inches(stat_width),
            Inches(0.6),
        )
        tf = label_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = stat.get("label", "")
        run.font.size = Pt(FONT_SIZE_STAT_LABEL)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        run.font.name = font_name

        # Context
        context = stat.get("context", "")
        if context:
            ctx_box = slide.shapes.add_textbox(
                Inches(sx),
                Inches(stat_top + 1.9),
                Inches(stat_width),
                Inches(0.5),
            )
            tf = ctx_box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            run = p.add_run()
            run.text = context
            run.font.size = Pt(FONT_SIZE_STAT_CONTEXT)
            run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)
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

    item_height = min(0.8, d["content_h"] / len(takeaways))
    start_y = d["content_top"] + 0.2

    for i, ta in enumerate(takeaways):
        iy = start_y + i * item_height

        # Icon/checkmark circle
        circle_size = 0.4
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(d["lm"] + 0.3),
            Inches(iy),
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
        run.text = ta.get("icon_hint", "✓")
        run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.name = font_name

        # Takeaway text
        txbox = slide.shapes.add_textbox(
            Inches(d["lm"] + 0.3 + circle_size + 0.3),
            Inches(iy),
            Inches(d["usable_w"] - circle_size - 0.9),
            Inches(circle_size),
        )
        tf = txbox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = ta.get("text", "")
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
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

    # Try placeholders first
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:
            ph.text = section_title
            for p in ph.text_frame.paragraphs:
                for run in p.runs:
                    run.font.name = font_name
            if section_subtitle:
                for ph2 in slide.placeholders:
                    if ph2.placeholder_format.idx == 1:
                        ph2.text = section_subtitle
                        for p in ph2.text_frame.paragraphs:
                            for run in p.runs:
                                run.font.name = font_name
                        break
            return

    # Fallback: manual layout
    # Section number
    if section_number:
        num_box = slide.shapes.add_textbox(
            Inches(d["lm"]),
            Inches(d["sh"] * 0.25),
            Inches(d["usable_w"]),
            Inches(0.8),
        )
        tf = num_box.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = f"SECTION {section_number}"
        run.font.size = Pt(FONT_SIZE_SMALL)
        run.font.bold = True
        run.font.color.rgb = accent
        run.font.name = font_name

    # Title
    title_box = slide.shapes.add_textbox(
        Inches(d["lm"]),
        Inches(d["sh"] * 0.35),
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
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    run.font.name = font_name

    # Accent line
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(d["sw"] / 2 - 1),
        Inches(d["sh"] * 0.55),
        Inches(2),
        Inches(0.04),
    )
    line.fill.solid()
    line.fill.fore_color.rgb = accent
    line.line.fill.background()

    # Subtitle
    if section_subtitle:
        sub_box = slide.shapes.add_textbox(
            Inches(d["lm"] + d["usable_w"] * 0.15),
            Inches(d["sh"] * 0.58),
            Inches(d["usable_w"] * 0.7),
            Inches(0.6),
        )
        tf = sub_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = section_subtitle
        run.font.size = Pt(FONT_SIZE_BODY)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        run.font.name = font_name

    logger.debug("Rendered section divider: %s", section_title)
