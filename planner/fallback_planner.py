"""
planner/fallback_planner.py — Rule-based fallback planner (no AI required).

Deterministically maps AST sections to slides when the Claude API is
unavailable or the user requests --no-ai mode.
"""

from __future__ import annotations

import logging
from typing import Any

from config import (
    SLIDE_COUNT_MIN,
    SLIDE_COUNT_MAX,
    SLIDE_COUNT_DEFAULT,
    MAX_BULLETS_PER_SLIDE,
    MAX_BULLET_WORDS,
    MIN_SECTION_WORD_COUNT,
)

logger = logging.getLogger(__name__)


def _truncate_words(text: str, max_words: int = MAX_BULLET_WORDS) -> str:
    """Truncate text to at most *max_words* words (6x6 / 7x7 rule)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def plan_slides_fallback(
    ast_dict: dict[str, Any],
    target_count: int = SLIDE_COUNT_DEFAULT,
    insights: Any = None,
) -> list[dict[str, Any]]:
    """Generate a slide plan using deterministic rules.

    Args:
        ast_dict: Structured AST dict from the parser.
        target_count: Desired number of slides.
        insights: Optional DocumentInsights from the insight engine.

    Returns:
        List of slide plan dicts.
    """
    target_count = max(SLIDE_COUNT_MIN, min(SLIDE_COUNT_MAX, target_count))
    sections = ast_dict.get("sections", [])
    metadata = ast_dict.get("metadata", {})
    title = ast_dict.get("title", "Presentation")

    slides: list[dict[str, Any]] = []
    slide_num = 1

    # ── Slide 1: Title ──
    slides.append({
        "slide_number": slide_num,
        "slide_type": "TITLE",
        "title": title,
        "subtitle": None,
        "content": {
            "headline": title,
            "subheadline": f"A {metadata.get('word_count', 0)}-word document overview",
            "presenter": None,
        },
        "speaker_notes": f"This presentation covers the key points from the document '{title}'.",
        "source_sections": [],
    })
    slide_num += 1

    # ── Slide 2: Agenda ──
    agenda_items = []
    section_headings = [s["heading"] for s in sections if s.get("heading")]
    for i, heading in enumerate(section_headings[:8], 1):
        agenda_items.append({"number": i, "topic": heading})

    if not agenda_items:
        agenda_items = [{"number": 1, "topic": "Overview"}]

    slides.append({
        "slide_number": slide_num,
        "slide_type": "AGENDA",
        "title": "Agenda",
        "subtitle": None,
        "content": {"items": agenda_items},
        "speaker_notes": "Here is what we will cover in this presentation.",
        "source_sections": [],
    })
    slide_num += 1

    # ── Slide 3: Executive Summary ──
    # Use insight engine if available, fall back to first-sentence extraction
    exec_insights: list[str] = []
    key_metric = None

    if insights and insights.executive_insights:
        exec_insights = insights.executive_insights[:4]
        key_metric = insights.key_metric
    else:
        for sec in sections[:4]:
            body = sec.get("body", "").strip()
            if body:
                first_sentence = body.split(".")[0].strip()
                if first_sentence and len(first_sentence) > 10:
                    exec_insights.append(first_sentence[:120] + ("..." if len(first_sentence) > 120 else ""))

        if metadata.get("has_numeric_data"):
            for sec in sections:
                for block in sec.get("blocks", []):
                    signals = block.get("data_signals", [])
                    for sig in signals:
                        if sig.get("type") in ("currency", "percentage"):
                            matches = sig.get("matches", [])
                            if matches:
                                key_metric = matches[0]
                                break
                    if key_metric:
                        break
                if key_metric:
                    break

    if not exec_insights:
        exec_insights = [f"Overview of {title}"]

    exec_speaker = "Let me walk you through the key findings."
    if insights and insights.executive_insights:
        exec_speaker = " ".join(
            (t if t.endswith(".") else t + ".") for t in insights.executive_insights[:2]
        )

    slides.append({
        "slide_number": slide_num,
        "slide_type": "EXEC_SUMMARY",
        "title": "Executive Summary",
        "subtitle": None,
        "content": {
            "insights": exec_insights[:4],
            "key_metric": key_metric,
        },
        "speaker_notes": exec_speaker,
        "source_sections": [s["heading"] for s in sections[:4]],
    })
    slide_num += 1

    # ── Content slides from sections ──
    # Skip sections that duplicate structural slides (TITLE, AGENDA, EXEC_SUMMARY)
    STRUCTURAL_HEADINGS = {
        "executive summary", "agenda", "table of contents",
        "conclusion", "summary",
    }
    content_sections = [
        s for s in _merge_small_sections(sections)
        if s.get("heading", "").lower().strip() not in STRUCTURAL_HEADINGS
    ]

    # Use extended slide range if we have more sections than the target allows
    from config import SLIDE_COUNT_EXTENDED_MAX
    slots_needed = len(content_sections) + 4  # +4 for TITLE, AGENDA, EXEC_SUMMARY, KEY_TAKEAWAYS
    effective_max = min(SLIDE_COUNT_EXTENDED_MAX, max(target_count, slots_needed))
    max_content_slide_num = effective_max - 1  # Reserve 1 for KEY_TAKEAWAYS

    # Determine which sections get which slide type
    for sec in content_sections:
        if slide_num > max_content_slide_num:
            break

        slide = _section_to_slide(sec, slide_num, insights=insights)
        if slide:
            # Enrich speaker notes with data insights
            if insights:
                sec_heading = sec.get("heading", "")
                si_notes = insights.get_speaker_notes(sec_heading)
                if si_notes:
                    slide["speaker_notes"] = si_notes
            slides.append(slide)
            slide_num += 1

    # If we need more slides, create section dividers
    while slide_num < target_count:
        slides.append({
            "slide_number": slide_num,
            "slide_type": "SECTION_DIVIDER",
            "title": "Summary",
            "subtitle": None,
            "content": {
                "section_number": slide_num - 2,
                "section_title": "Key Details",
                "section_subtitle": "Additional analysis",
            },
            "speaker_notes": "Let's review the additional details.",
            "source_sections": [],
        })
        slide_num += 1

    # ── Last slide: Key Takeaways ──
    takeaways = []

    # Use insight engine takeaways if available
    if insights and insights.takeaways:
        for t in insights.takeaways[:5]:
            takeaways.append({
                "icon_hint": t.icon_hint,
                "text": _truncate_words(t.text, max_words=12),
            })
    else:
        for sec in sections:
            body = sec.get("body", "").strip()
            if body:
                first_line = body.split("\n")[0].strip().split(".")[0].strip()
                if first_line and len(first_line) > 10:
                    takeaways.append({
                        "icon_hint": "✓",
                        "text": _truncate_words(first_line, max_words=10),
                    })
                if len(takeaways) >= 5:
                    break

    if not takeaways:
        takeaways = [{"icon_hint": "✓", "text": f"Review the full {title} document for details"}]

    slides.append({
        "slide_number": slide_num,
        "slide_type": "KEY_TAKEAWAYS",
        "title": "Key Takeaways",
        "subtitle": None,
        "content": {"takeaways": takeaways[:5]},
        "speaker_notes": "These are the top takeaways from our presentation.",
        "source_sections": [],
    })

    # Renumber slides
    for i, slide in enumerate(slides):
        slide["slide_number"] = i + 1

    logger.info("Fallback planner generated %d slides", len(slides))
    return slides


def _section_to_slide(
    section: dict[str, Any],
    slide_num: int,
    insights: Any = None,
) -> dict[str, Any] | None:
    """Convert a single AST section into the best-fit slide type.

    Args:
        section: AST section dict.
        slide_num: Current slide number.
        insights: Optional DocumentInsights for enriched speaker notes.

    Returns:
        A slide plan dict, or None if the section is empty.
    """
    heading = section.get("heading", "Section")
    blocks = section.get("blocks", [])
    body = section.get("body", "").strip()

    # Get insight-enriched speaker notes if available
    speaker_notes = f"Key points about {heading}."
    if insights:
        si_notes = insights.get_speaker_notes(heading)
        if si_notes:
            speaker_notes = si_notes

    if not blocks and not body:
        return None

    # Check for table blocks — also detect chart-worthy tables
    for block in blocks:
        if block["type"] == "table":
            content = block.get("content", {})
            headers = content.get("headers", [])
            rows = content.get("rows", [])
            if headers and rows:
                # Check if this table has numeric columns → generate bar chart
                from parser.data_detector import detect_table_chart_potential
                chart_potential = detect_table_chart_potential(headers, rows)
                if chart_potential and chart_potential.get("chart_hint") == "PIE_CHART":
                    return _make_pie_chart_slide(heading, content, slide_num)
                elif chart_potential and chart_potential.get("chart_hint") == "LINE_CHART":
                    return _make_line_chart_from_table(heading, content, chart_potential, slide_num)
                elif chart_potential and chart_potential.get("chart_hint") == "BAR_CHART":
                    return _make_bar_chart_from_table(heading, content, chart_potential, slide_num)
                # Otherwise render as plain table
                return {
                    "slide_number": slide_num,
                    "slide_type": "TABLE",
                    "title": heading,
                    "subtitle": None,
                    "content": {
                        "table_title": heading,
                        "headers": headers,
                        "rows": rows[:12],
                    },
                    "speaker_notes": f"This table shows data related to {heading}.",
                    "source_sections": [heading],
                }

    # Check for chart-worthy data signals
    for block in blocks:
        signals = block.get("data_signals", [])
        for sig in signals:
            chart_hint = sig.get("chart_hint", "")
            if chart_hint == "PIE_CHART" and block["type"] == "table":
                table_content = block.get("content", {})
                return _make_pie_chart_slide(heading, table_content, slide_num)
            elif chart_hint in ("BAR_CHART", "LINE_CHART"):
                # Create a stat highlight as fallback (we don't have clean data without AI)
                stats = _extract_stats_from_signals(signals)
                if stats:
                    return {
                        "slide_number": slide_num,
                        "slide_type": "STAT_HIGHLIGHT",
                        "title": heading,
                        "subtitle": None,
                        "content": {"stats": stats[:3]},
                        "speaker_notes": f"Key statistics from {heading}.",
                        "source_sections": [heading],
                    }

    # Check for list blocks → bullet slide
    bullet_items = []
    for block in blocks:
        if block["type"] in ("bullet_list", "ordered_list"):
            items = block.get("content", [])
            for item in items:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                if text.strip():
                    sub_bullets = None
                    if isinstance(item, dict) and "children" in item:
                        sub_bullets = [
                            c.get("text", "") for c in item["children"]
                            if isinstance(c, dict)
                        ]
                    bullet_items.append({
                        "text": _truncate_words(text),
                        "sub_bullets": sub_bullets,
                    })

    if bullet_items:
        return {
            "slide_number": slide_num,
            "slide_type": "CONTENT_BULLETS",
            "title": heading,
            "subtitle": None,
            "content": {"bullets": bullet_items[:MAX_BULLETS_PER_SLIDE]},
            "speaker_notes": f"Key points about {heading}.",
            "source_sections": [heading],
        }

    # Default: paragraph → bullet points from sentences
    sentences = [s.strip() for s in body.split(".") if s.strip() and len(s.strip()) > 10]
    if sentences:
        bullet_items = [{"text": _truncate_words(s), "sub_bullets": None} for s in sentences[:MAX_BULLETS_PER_SLIDE]]
        return {
            "slide_number": slide_num,
            "slide_type": "CONTENT_BULLETS",
            "title": heading,
            "subtitle": None,
            "content": {"bullets": bullet_items},
            "speaker_notes": f"Summary of {heading}.",
            "source_sections": [heading],
        }

    return None


def _merge_small_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge sections that are too short to warrant their own slide.

    Args:
        sections: List of AST section dicts.

    Returns:
        Merged list of sections.
    """
    if len(sections) <= 1:
        return sections

    merged: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None

    for sec in sections:
        word_count = len(sec.get("body", "").split())

        if word_count < MIN_SECTION_WORD_COUNT and pending is not None:
            # Merge into pending
            pending["body"] += "\n" + sec.get("body", "")
            pending["blocks"].extend(sec.get("blocks", []))
            logger.debug("Merged small section '%s' into '%s'", sec["heading"], pending["heading"])
        elif word_count < MIN_SECTION_WORD_COUNT and pending is None:
            pending = dict(sec)
            pending["blocks"] = list(sec.get("blocks", []))
        else:
            if pending is not None:
                # Merge pending into this section
                sec_copy = dict(sec)
                sec_copy["body"] = pending.get("body", "") + "\n" + sec.get("body", "")
                sec_copy["blocks"] = pending.get("blocks", []) + sec.get("blocks", [])
                merged.append(sec_copy)
                pending = None
            else:
                merged.append(sec)

    if pending is not None:
        if merged:
            merged[-1]["body"] += "\n" + pending.get("body", "")
            merged[-1]["blocks"].extend(pending.get("blocks", []))
        else:
            merged.append(pending)

    return merged


def _extract_stats_from_signals(signals: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract stat-highlight data from data signals.

    Args:
        signals: List of data signal dicts.

    Returns:
        List of stat dicts with value, label, context.
    """
    stats: list[dict[str, str]] = []
    for sig in signals:
        matches = sig.get("matches", [])
        sig_type = sig.get("type", "")
        for match in matches[:3]:
            stats.append({
                "value": str(match),
                "label": sig_type.replace("_", " ").title(),
                "context": "",
            })
            if len(stats) >= 3:
                return stats
    return stats


def _make_bar_chart_from_table(
    heading: str,
    table_content: dict[str, Any],
    chart_potential: dict[str, Any],
    slide_num: int,
) -> dict[str, Any]:
    """Create a bar chart slide from table data with numeric columns.

    Args:
        heading: Section heading.
        table_content: Table content with headers and rows.
        chart_potential: Chart potential info from detect_table_chart_potential.
        slide_num: Current slide number.

    Returns:
        Bar chart slide plan dict.
    """
    headers = table_content.get("headers", [])
    rows = table_content.get("rows", [])
    label_col = chart_potential.get("label_column")
    numeric_cols = chart_potential.get("numeric_columns", [])

    # Find label column index
    label_idx = 0
    if label_col and label_col in headers:
        label_idx = headers.index(label_col)

    series = []
    for num_col_name in numeric_cols[:3]:
        if num_col_name in headers:
            col_idx = headers.index(num_col_name)
            values = []
            for row in rows:
                if label_idx < len(row) and col_idx < len(row):
                    cell = row[col_idx].strip().replace(",", "").replace("$", "").replace("%", "").replace("+", "")
                    try:
                        values.append([row[label_idx], float(cell)])
                    except (ValueError, TypeError):
                        continue
            if values:
                series.append({"name": num_col_name, "values": values})

    if not series:
        return {
            "slide_number": slide_num,
            "slide_type": "TABLE",
            "title": heading,
            "subtitle": None,
            "content": {
                "table_title": heading,
                "headers": headers,
                "rows": rows[:12],
            },
            "speaker_notes": f"Data for {heading}.",
            "source_sections": [heading],
        }

    return {
        "slide_number": slide_num,
        "slide_type": "BAR_CHART",
        "title": heading,
        "subtitle": None,
        "content": {
            "chart_title": heading,
            "series": series,
            "x_label": label_col or "",
            "y_label": "",
        },
        "speaker_notes": f"Bar chart showing {heading} data.",
        "source_sections": [heading],
    }


def _make_line_chart_from_table(
    heading: str,
    table_content: dict[str, Any],
    chart_potential: dict[str, Any],
    slide_num: int,
) -> dict[str, Any]:
    """Create a line chart slide from time-series table data.

    Args:
        heading: Section heading.
        table_content: Table content with headers and rows.
        chart_potential: Chart potential info from detect_table_chart_potential.
        slide_num: Current slide number.

    Returns:
        Line chart slide plan dict.
    """
    headers = table_content.get("headers", [])
    rows = table_content.get("rows", [])
    label_col = chart_potential.get("label_column")
    numeric_cols = chart_potential.get("numeric_columns", [])

    label_idx = 0
    if label_col and label_col in headers:
        label_idx = headers.index(label_col)

    series = []
    for num_col_name in numeric_cols[:3]:
        if num_col_name in headers:
            col_idx = headers.index(num_col_name)
            points = []
            for row in rows:
                if label_idx < len(row) and col_idx < len(row):
                    cell = row[col_idx].strip().replace(",", "").replace("$", "").replace("%", "").replace("+", "")
                    try:
                        x_val = row[label_idx].strip()
                        points.append([x_val, float(cell)])
                    except (ValueError, TypeError):
                        continue
            if points:
                series.append({"name": num_col_name, "points": points})

    if not series:
        return _make_bar_chart_from_table(heading, table_content, chart_potential, slide_num)

    return {
        "slide_number": slide_num,
        "slide_type": "LINE_CHART",
        "title": heading,
        "subtitle": None,
        "content": {
            "chart_title": heading,
            "series": series,
            "x_label": label_col or "",
            "y_label": numeric_cols[0] if numeric_cols else "",
        },
        "speaker_notes": f"Line chart showing {heading} trends over time.",
        "source_sections": [heading],
    }


def _make_pie_chart_slide(
    heading: str,
    table_content: dict[str, Any],
    slide_num: int,
) -> dict[str, Any]:
    """Create a pie chart slide from table data.

    Args:
        heading: Section heading.
        table_content: Table content with headers and rows.
        slide_num: Current slide number.

    Returns:
        Pie chart slide plan dict.
    """
    headers = table_content.get("headers", [])
    rows = table_content.get("rows", [])

    slices = []
    for row in rows[:8]:
        if len(row) >= 2:
            label = row[0]
            try:
                value = float(row[1].replace(",", "").replace("$", "").replace("%", ""))
                slices.append({"label": label, "value": value})
            except (ValueError, IndexError):
                continue

    if not slices:
        # Fallback to bullet slide
        return {
            "slide_number": slide_num,
            "slide_type": "CONTENT_BULLETS",
            "title": heading,
            "subtitle": None,
            "content": {"bullets": [{"text": " | ".join(row), "sub_bullets": None} for row in rows[:5]]},
            "speaker_notes": f"Data overview for {heading}.",
            "source_sections": [heading],
        }

    return {
        "slide_number": slide_num,
        "slide_type": "PIE_CHART",
        "title": heading,
        "subtitle": None,
        "content": {
            "chart_title": heading,
            "slices": slices,
        },
        "speaker_notes": f"Distribution chart for {heading}.",
        "source_sections": [heading],
    }
