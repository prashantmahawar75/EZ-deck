"""
builder/slide_factory.py — Creates individual slides by type.

Each slide type has a dedicated create_slide_* function. All positions
are computed as fractions of slide dimensions — no hardcoded values.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

from builder.layout_manager import LayoutManager
from builder.style_constants import MasterStyle
from renderers.content_renderer import (
    render_title_slide,
    render_agenda_slide,
    render_exec_summary_slide,
    render_bullets_slide,
    render_two_column_slide,
    render_stat_highlight_slide,
    render_key_takeaways_slide,
    render_section_divider_slide,
)
from renderers.chart_renderer import (
    render_bar_chart,
    render_pie_chart,
    render_line_chart,
    render_area_chart,
)
from renderers.infographic_renderer import (
    render_timeline,
    render_process_flow,
    render_comparison,
)
from renderers.table_renderer import render_table

from config import (
    SLIDE_WIDTH_INCHES,
    SLIDE_HEIGHT_INCHES,
    MARGIN_LEFT_FRAC,
    MARGIN_RIGHT_FRAC,
    TITLE_TOP_FRAC,
    TITLE_HEIGHT_FRAC,
    CONTENT_TOP_FRAC,
    CONTENT_HEIGHT_FRAC,
    FONT_SIZE_TITLE,
)

logger = logging.getLogger(__name__)


def create_slide(
    slide_plan_item: dict[str, Any],
    prs: Presentation,
    layout_mgr: LayoutManager,
    style: MasterStyle,
) -> list[Any]:
    """Create one or more slides from a slide plan item.

    Returns multiple slides when content overflows (e.g., large tables).

    Args:
        slide_plan_item: Dict from the slide plan with slide_type, title, content, etc.
        prs: python-pptx Presentation object.
        layout_mgr: LayoutManager for selecting layouts.
        style: MasterStyle with theme colors/fonts.

    Returns:
        List of created slide objects.
    """
    slide_type = slide_plan_item.get("slide_type", "CONTENT_BULLETS")
    title = slide_plan_item.get("title", "")
    content = slide_plan_item.get("content", {})
    speaker_notes = slide_plan_item.get("speaker_notes", "")

    # Get the layout
    layout = layout_mgr.get_layout(slide_type)
    slide = prs.slides.add_slide(layout)

    # Set slide title via placeholder if available
    _set_slide_title(slide, title, style)

    # Add speaker notes
    if speaker_notes:
        _add_speaker_notes(slide, speaker_notes)

    # Dispatch to the appropriate renderer
    created_slides = [slide]

    try:
        if slide_type == "TITLE":
            render_title_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "AGENDA":
            render_agenda_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "EXEC_SUMMARY":
            render_exec_summary_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "CONTENT_BULLETS":
            render_bullets_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "CONTENT_TWO_COLUMN":
            render_two_column_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "STAT_HIGHLIGHT":
            render_stat_highlight_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "BAR_CHART":
            _create_chart_slide(slide, content, "bar", style, prs)

        elif slide_type == "PIE_CHART":
            _create_chart_slide(slide, content, "pie", style, prs)

        elif slide_type == "LINE_CHART":
            _create_chart_slide(slide, content, "line", style, prs)

        elif slide_type == "AREA_CHART":
            _create_chart_slide(slide, content, "area", style, prs)

        elif slide_type == "TABLE":
            extra = _create_table_slide(slide, content, style, prs, layout_mgr)
            created_slides.extend(extra)

        elif slide_type == "TIMELINE_INFOGRAPHIC":
            events = content.get("events", [])
            render_timeline(events, slide, style.accent_color, style.font_name)

        elif slide_type == "PROCESS_FLOW_INFOGRAPHIC":
            steps = content.get("steps", [])
            direction = content.get("flow_direction", "horizontal")
            render_process_flow(steps, slide, direction, style.accent_color, style.font_name)

        elif slide_type == "COMPARISON_INFOGRAPHIC":
            render_comparison(
                content.get("left_label", "Option A"),
                content.get("right_label", "Option B"),
                content.get("dimensions", []),
                slide,
                style.accent_color,
                style.font_name,
            )

        elif slide_type == "KEY_TAKEAWAYS":
            render_key_takeaways_slide(content, slide, style.accent_color, style.font_name)

        elif slide_type == "SECTION_DIVIDER":
            render_section_divider_slide(content, slide, style.accent_color, style.font_name)

        else:
            logger.warning("Unknown slide type '%s', rendering as bullets", slide_type)
            render_bullets_slide(content, slide, style.accent_color, style.font_name)

    except Exception as exc:
        logger.error(
            "Error rendering slide %d (%s): %s",
            slide_plan_item.get("slide_number", 0), slide_type, exc,
        )
        # Add error indicator text
        _add_error_text(slide, f"Rendering error: {exc}", style)

    logger.info(
        "Created slide %d: %s — '%s'",
        slide_plan_item.get("slide_number", 0), slide_type, title,
    )
    return created_slides


def _set_slide_title(slide: Any, title: str, style: MasterStyle) -> None:
    """Set the slide's title using the title placeholder if available.

    Args:
        slide: python-pptx slide object.
        title: Title text.
        style: MasterStyle for font info.
    """
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:  # Title placeholder
            ph.text = title
            for p in ph.text_frame.paragraphs:
                for run in p.runs:
                    run.font.name = style.font_name
            return

    # No title placeholder — add a text box at the top
    sw = SLIDE_WIDTH_INCHES
    sh = SLIDE_HEIGHT_INCHES
    lm = sw * MARGIN_LEFT_FRAC
    rm = sw * MARGIN_RIGHT_FRAC

    txbox = slide.shapes.add_textbox(
        Inches(lm),
        Inches(sh * TITLE_TOP_FRAC),
        Inches(sw - lm - rm),
        Inches(sh * TITLE_HEIGHT_FRAC),
    )
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = title
    run.font.size = Pt(FONT_SIZE_TITLE)
    run.font.bold = True
    run.font.color.rgb = style.dark_text
    run.font.name = style.font_name


def _add_speaker_notes(slide: Any, notes: str) -> None:
    """Add speaker notes to a slide.

    Args:
        slide: python-pptx slide object.
        notes: Speaker notes text.
    """
    try:
        notes_slide = slide.notes_slide
        notes_tf = notes_slide.notes_text_frame
        notes_tf.text = notes
    except Exception as exc:
        logger.debug("Could not add speaker notes: %s", exc)


def _create_chart_slide(
    slide: Any,
    content: dict[str, Any],
    chart_type: str,
    style: MasterStyle,
    prs: Presentation,
) -> None:
    """Render a chart and add it to the slide as an image.

    Args:
        slide: python-pptx slide object.
        content: Chart content dict.
        chart_type: One of "bar", "pie", "line", "area".
        style: MasterStyle with palette.
        prs: Presentation object.
    """
    chart_title = content.get("chart_title", "")
    x_label = content.get("x_label", "")
    y_label = content.get("y_label", "")

    try:
        if chart_type == "bar":
            series = content.get("series", [])
            img_buf = render_bar_chart(
                series, x_label, y_label, chart_title,
                palette=style.chart_palette,
                font_family=style.font_name,
            )

        elif chart_type == "pie":
            slices = content.get("slices", [])
            img_buf = render_pie_chart(
                slices, chart_title,
                palette=style.chart_palette,
                font_family=style.font_name,
            )

        elif chart_type == "line":
            series = content.get("series", [])
            img_buf = render_line_chart(
                series, x_label, y_label, chart_title,
                palette=style.chart_palette,
                font_family=style.font_name,
            )

        elif chart_type == "area":
            series = content.get("series", [])
            img_buf = render_area_chart(
                series, x_label, y_label, chart_title,
                palette=style.chart_palette,
                font_family=style.font_name,
            )

        else:
            logger.warning("Unknown chart type: %s", chart_type)
            return

        # Add chart image to slide
        sw = SLIDE_WIDTH_INCHES
        sh = SLIDE_HEIGHT_INCHES
        content_top = sh * CONTENT_TOP_FRAC
        content_h = sh * CONTENT_HEIGHT_FRAC
        lm = sw * MARGIN_LEFT_FRAC
        rm = sw * MARGIN_RIGHT_FRAC
        usable_w = sw - lm - rm

        # Center the chart image
        img_width = usable_w * 0.85
        img_height = content_h * 0.85
        img_left = lm + (usable_w - img_width) / 2
        img_top = content_top + (content_h - img_height) / 2

        pic = slide.shapes.add_picture(
            img_buf,
            Inches(img_left),
            Inches(img_top),
            Inches(img_width),
            Inches(img_height),
        )

        # Set alt text for accessibility
        pic.name = f"{chart_type}_chart"
        # Alt text via XML for python-pptx compatibility
        try:
            from lxml import etree
            nvSpPr = pic._element.find(
                ".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
            )
            if nvSpPr is None:
                nvSpPr = pic._element.find(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}cNvPr"
                )
            if nvSpPr is None:
                # Try the picture-specific path
                for elem in pic._element.iter():
                    if elem.tag.endswith("}cNvPr"):
                        nvSpPr = elem
                        break
            if nvSpPr is not None:
                nvSpPr.set("descr", f"{chart_type.title()} chart: {chart_title}")
        except Exception:
            pass

        logger.info("Added %s chart image to slide", chart_type)

    except Exception as exc:
        logger.error("Failed to render %s chart: %s", chart_type, exc)
        _add_error_text(slide, f"Chart rendering failed: {exc}", style)


def _create_table_slide(
    slide: Any,
    content: dict[str, Any],
    style: MasterStyle,
    prs: Presentation,
    layout_mgr: LayoutManager,
) -> list[Any]:
    """Create a table slide, handling overflow with additional slides.

    Args:
        slide: python-pptx slide object for the first page.
        content: Table content dict.
        style: MasterStyle.
        prs: Presentation object.
        layout_mgr: LayoutManager.

    Returns:
        List of additional slides created for overflow.
    """
    headers = content.get("headers", [])
    rows = content.get("rows", [])
    table_title = content.get("table_title", "")

    extra_slides: list[Any] = []

    remaining_pages = render_table(
        headers, rows, slide, table_title,
        accent_color=style.accent_color,
        font_name=style.font_name,
    )

    # Create additional slides for overflow pages
    for page_rows in remaining_pages:
        extra_layout = layout_mgr.get_layout("TABLE")
        extra_slide = prs.slides.add_slide(extra_layout)
        _set_slide_title(extra_slide, f"{table_title} (cont.)", style)
        render_table(
            headers, page_rows, extra_slide, f"{table_title} (continued)",
            accent_color=style.accent_color,
            font_name=style.font_name,
        )
        extra_slides.append(extra_slide)

    return extra_slides


def _add_error_text(slide: Any, error_msg: str, style: MasterStyle) -> None:
    """Add an error message to a slide (for debugging/fallback).

    Args:
        slide: python-pptx slide object.
        error_msg: Error message to display.
        style: MasterStyle for font info.
    """
    sw = SLIDE_WIDTH_INCHES
    sh = SLIDE_HEIGHT_INCHES

    txbox = slide.shapes.add_textbox(
        Inches(sw * 0.1),
        Inches(sh * 0.4),
        Inches(sw * 0.8),
        Inches(sh * 0.2),
    )
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = f"[!] {error_msg}"
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0xCC, 0x33, 0x33)
    run.font.name = style.font_name
