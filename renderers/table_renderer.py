"""
renderers/table_renderer.py — Renders markdown tables as styled pptx tables.

Uses python-pptx table objects with themed header rows, alternating tints,
proper cell padding, and auto-sized columns.
"""

from __future__ import annotations

import logging
from typing import Any

from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor

from config import (
    SLIDE_WIDTH_INCHES,
    SLIDE_HEIGHT_INCHES,
    MARGIN_LEFT_FRAC,
    MARGIN_RIGHT_FRAC,
    CONTENT_TOP_FRAC,
    CONTENT_HEIGHT_FRAC,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS_PER_SLIDE,
    FONT_SIZE_SMALL,
    FONT_SIZE_FOOTNOTE,
)

logger = logging.getLogger(__name__)

CELL_PADDING = Inches(0.08)


def render_table(
    headers: list[str],
    rows: list[list[str]],
    slide: Any,
    title: str = "",
    accent_color: RGBColor | None = None,
    font_name: str = "Calibri",
) -> list[list[list[str]]]:
    """Render a table on the given slide.

    If the table exceeds MAX_TABLE_ROWS_PER_SLIDE, only the first page is
    rendered and remaining row groups are returned for additional slides.

    If the table exceeds MAX_TABLE_COLUMNS, columns are split across tables.

    Args:
        headers: Column header strings.
        rows: 2D list of cell strings.
        slide: python-pptx slide object.
        title: Optional table title.
        accent_color: Header background color.
        font_name: Font family.

    Returns:
        List of remaining row pages (each is a list of rows). Empty if
        all rows fit on one slide.
    """
    accent = accent_color or RGBColor(0x2E, 0x86, 0xAB)
    white = RGBColor(0xFF, 0xFF, 0xFF)
    dark_text = RGBColor(0x33, 0x33, 0x33)
    alt_row_bg = RGBColor(0xF5, 0xF7, 0xFA)
    white_bg = RGBColor(0xFF, 0xFF, 0xFF)

    # Handle column overflow
    if len(headers) > MAX_TABLE_COLUMNS:
        logger.warning(
            "Table has %d columns (max %d), truncating", len(headers), MAX_TABLE_COLUMNS
        )
        headers = headers[:MAX_TABLE_COLUMNS]
        rows = [row[:MAX_TABLE_COLUMNS] for row in rows]

    # Handle row overflow — render first page, return remaining
    remaining_pages: list[list[list[str]]] = []
    if len(rows) > MAX_TABLE_ROWS_PER_SLIDE:
        for i in range(MAX_TABLE_ROWS_PER_SLIDE, len(rows), MAX_TABLE_ROWS_PER_SLIDE):
            remaining_pages.append(rows[i:i + MAX_TABLE_ROWS_PER_SLIDE])
        rows = rows[:MAX_TABLE_ROWS_PER_SLIDE]

        # Add footer note about truncation
        logger.info("Table paginated: %d rows on this slide, %d pages remaining",
                     len(rows), len(remaining_pages))

    # Normalize rows (ensure all have same column count)
    num_cols = len(headers)
    for i, row in enumerate(rows):
        if len(row) < num_cols:
            rows[i] = row + [""] * (num_cols - len(row))
        elif len(row) > num_cols:
            rows[i] = row[:num_cols]

    # Calculate dimensions
    sw = SLIDE_WIDTH_INCHES
    sh = SLIDE_HEIGHT_INCHES
    left_margin = sw * MARGIN_LEFT_FRAC
    right_margin = sw * MARGIN_RIGHT_FRAC
    usable_width = sw - left_margin - right_margin

    content_top = sh * CONTENT_TOP_FRAC
    content_height = sh * CONTENT_HEIGHT_FRAC

    # Estimate column widths based on content
    col_widths = _estimate_column_widths(headers, rows, usable_width)

    table_width = sum(col_widths)
    table_left = left_margin + (usable_width - table_width) / 2  # Center table

    num_rows = len(rows) + 1  # +1 for header
    row_height = min(0.45, content_height / num_rows)
    table_height = row_height * num_rows

    # Vertical centering of table within content area
    table_top = content_top + (content_height - table_height) / 2
    table_top = max(content_top, table_top)

    # Create the table
    table_shape = slide.shapes.add_table(
        num_rows,
        num_cols,
        Inches(table_left),
        Inches(table_top),
        Inches(table_width),
        Inches(table_height),
    )
    table = table_shape.table

    # Set column widths
    for col_idx, width in enumerate(col_widths):
        table.columns[col_idx].width = Inches(width)

    # Style the header row
    for col_idx, header_text in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = ""  # Clear default
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = header_text
        run.font.size = Pt(FONT_SIZE_SMALL)
        run.font.bold = True
        run.font.color.rgb = white
        run.font.name = font_name

        # Header background
        cell.fill.solid()
        cell.fill.fore_color.rgb = accent

        # Cell margins
        cell.margin_left = CELL_PADDING
        cell.margin_right = CELL_PADDING
        cell.margin_top = CELL_PADDING
        cell.margin_bottom = CELL_PADDING
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Style data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_text in enumerate(row_data):
            cell = table.cell(row_idx + 1, col_idx)
            cell.text = ""
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if col_idx == 0 else PP_ALIGN.CENTER
            run = p.add_run()
            run.text = str(cell_text)
            run.font.size = Pt(FONT_SIZE_SMALL)
            run.font.color.rgb = dark_text
            run.font.name = font_name

            # Alternating row colors
            cell.fill.solid()
            cell.fill.fore_color.rgb = alt_row_bg if row_idx % 2 == 0 else white_bg

            cell.margin_left = CELL_PADDING
            cell.margin_right = CELL_PADDING
            cell.margin_top = CELL_PADDING
            cell.margin_bottom = CELL_PADDING
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Add truncation footnote if there are remaining pages
    if remaining_pages:
        from pptx.util import Inches as In
        footnote = slide.shapes.add_textbox(
            Inches(left_margin),
            Inches(table_top + table_height + 0.1),
            Inches(usable_width),
            Inches(0.3),
        )
        tf = footnote.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        run = p.add_run()
        run.text = f"Showing first {len(rows)} rows. See appendix for full data."
        run.font.size = Pt(FONT_SIZE_FOOTNOTE)
        run.font.italic = True
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        run.font.name = font_name

    logger.info("Rendered table: %d cols × %d rows", num_cols, len(rows))
    return remaining_pages


def _estimate_column_widths(
    headers: list[str],
    rows: list[list[str]],
    max_total: float,
) -> list[float]:
    """Estimate column widths based on content length.

    Args:
        headers: Column headers.
        rows: Data rows.
        max_total: Maximum total width in inches.

    Returns:
        List of column widths in inches.
    """
    num_cols = len(headers)
    if num_cols == 0:
        return []

    # Compute max char count per column
    max_chars = [len(h) for h in headers]
    for row in rows:
        for col_idx, cell in enumerate(row):
            if col_idx < num_cols:
                max_chars[col_idx] = max(max_chars[col_idx], len(str(cell)))

    # Convert chars to proportional widths
    total_chars = sum(max_chars) or 1
    min_width = 0.8  # Minimum column width

    widths = []
    for chars in max_chars:
        w = max(min_width, (chars / total_chars) * max_total)
        widths.append(w)

    # Scale to fit max_total
    total = sum(widths)
    if total > max_total:
        scale = max_total / total
        widths = [w * scale for w in widths]

    return widths
