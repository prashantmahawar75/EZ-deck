"""
parser/data_detector.py — Detects chart-worthy data patterns in text content.

Scans for currency values, percentages, year-indexed data, and numeric
comparison tables to signal which sections are candidates for chart slides.
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Compiled regex patterns
# ──────────────────────────────────────────────

# Currency: $1.2M, ₹50,000, €2B, £400K, $12,345.67
CURRENCY_PATTERN = re.compile(
    r'[\$€£₹¥]\s*\d[\d,]*\.?\d*\s*[KkMmBbTt]?(?:illion|illion)?'
    r'|'
    r'\d[\d,]*\.?\d*\s*(?:USD|EUR|GBP|INR|JPY)',
    re.IGNORECASE
)

# Percentages: 45%, 12.5%, 100 percent
PERCENTAGE_PATTERN = re.compile(
    r'\d+\.?\d*\s*%'
    r'|'
    r'\d+\.?\d*\s+percent',
    re.IGNORECASE
)

# Year references: 2019, 2020, 2021 (4-digit years in plausible range)
YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')

# Generic numbers (for numeric density detection)
NUMBER_PATTERN = re.compile(r'\b\d+\.?\d*\b')

# BUG 6 FIX: Pattern to detect bullet lists with year:value format
# Matches: "- 2019: 12%", "- 2020: -7%", "- 2021: $45M"
BULLET_NUMERIC_PATTERN = re.compile(
    r'^[-*•]\s*(\d{4})\s*:\s*([+-]?\$?€?£?[\d,.]+)\s*[%KMBkmb]?.*$',
    re.MULTILINE
)


def parse_bullet_as_chart_data(lines: list[str]) -> list[dict[str, Any]] | None:
    """BUG 6 FIX: Parse bullet list lines into chart-ready data.
    
    Detects patterns like:
    - 2019: 12%
    - 2020: -7%
    - 2021: 23%
    
    Args:
        lines: List of bullet point text lines.
        
    Returns:
        List of {year, value} dicts if pattern matches, else None.
    """
    results = []
    year_value_pattern = re.compile(r'^(\d{4})\s*:\s*([+-]?\$?€?£?[\d,.]+)\s*[%KMBkmb]?')
    
    for line in lines:
        # Strip bullet markers
        cleaned = re.sub(r'^[-*•]\s*', '', line.strip())
        m = year_value_pattern.match(cleaned)
        if not m:
            return None  # Not a numeric bullet list
        
        try:
            year = int(m.group(1))
            # Clean value: remove currency symbols and commas
            val_str = m.group(2).replace('$', '').replace('€', '').replace('£', '').replace(',', '')
            value = float(val_str)
            results.append({"year": year, "value": value})
        except (ValueError, TypeError):
            return None
    
    # Need at least 3 data points for a meaningful chart
    return results if len(results) >= 3 else None


def should_be_chart(table_data: list[dict[str, Any]], headers: list[str] | None = None) -> tuple[bool, str]:
    """BUG 4 & 7 FIX: Strict decision function for chart vs table rendering.
    
    Args:
        table_data: List of row dicts with column values.
        headers: Optional column headers for semantic analysis.
        
    Returns:
        Tuple of (should_render_as_chart, chart_type).
        chart_type is one of: "line", "pie", "bar", "table"
    """
    if not table_data:
        return False, "table"
    
    columns = list(table_data[0].keys())
    if len(columns) < 2:
        return False, "table"
    
    first_col = columns[0]
    second_col = columns[1]
    first_col_values = [row.get(first_col, "") for row in table_data]
    second_col_values = [row.get(second_col, "") for row in table_data]
    
    # Rule 1: If first column is year-like (2000-2035), it's a TIME SERIES → line chart
    try:
        years = [int(str(v).strip()) for v in first_col_values]
        if all(2000 <= y <= 2035 for y in years):
            return True, "line"
    except (ValueError, TypeError):
        pass
    
    # Rule 2: BUG 7 FIX - If second column header contains share/allocation/distribution → pie chart
    if headers and len(headers) >= 2:
        second_header_lower = headers[1].lower()
        pie_keywords = ["share", "%", "percent", "allocation", "distribution", "portion", "ratio"]
        if any(kw in second_header_lower for kw in pie_keywords):
            return True, "pie"
    
    # Also check if values look like percentages
    pct_count = 0
    for v in second_col_values:
        v_str = str(v).strip()
        if '%' in v_str or v_str.endswith('percent'):
            pct_count += 1
    if pct_count >= len(second_col_values) * 0.7:
        return True, "pie"
    
    # Rule 3: If rows are named entities with one numeric column → bar chart
    try:
        # Check if second column is numeric
        for v in second_col_values:
            cleaned = str(v).replace('%', '').replace('$', '').replace(',', '').strip()
            float(cleaned)
        return True, "bar"
    except (ValueError, TypeError):
        pass
    
    return False, "table"


def detect_data_signals(text: str) -> list[dict[str, Any]]:
    """Analyze text for data visualization signals.

    Args:
        text: Raw text content to scan for numeric patterns.

    Returns:
        List of signal dicts, each with keys:
          - "type": str — one of "currency", "percentage", "year_series",
                          "numeric_density"
          - "matches": list[str] — the matched substrings
          - "chart_hint": str — suggested chart type
          - "confidence": float — 0.0 to 1.0
    """
    signals: list[dict[str, Any]] = []

    # --- Currency detection ---
    currency_matches = CURRENCY_PATTERN.findall(text)
    if currency_matches:
        signals.append({
            "type": "currency",
            "matches": currency_matches,
            "chart_hint": "BAR_CHART" if len(currency_matches) >= 3 else "STAT_HIGHLIGHT",
            "confidence": min(1.0, len(currency_matches) * 0.25),
        })
        logger.debug("Detected %d currency values", len(currency_matches))

    # --- Percentage detection ---
    pct_matches = PERCENTAGE_PATTERN.findall(text)
    if pct_matches:
        # Multiple percentages suggest pie chart; few suggest stat highlight
        if len(pct_matches) >= 3:
            chart_hint = "PIE_CHART"
        elif len(pct_matches) >= 2:
            chart_hint = "BAR_CHART"
        else:
            chart_hint = "STAT_HIGHLIGHT"
        signals.append({
            "type": "percentage",
            "matches": pct_matches,
            "chart_hint": chart_hint,
            "confidence": min(1.0, len(pct_matches) * 0.3),
        })
        logger.debug("Detected %d percentage values", len(pct_matches))

    # --- Year-indexed series ---
    year_matches = list(set(YEAR_PATTERN.findall(text)))
    if len(year_matches) >= 2:
        signals.append({
            "type": "year_series",
            "matches": sorted(year_matches),
            "chart_hint": "LINE_CHART",
            "confidence": min(1.0, len(year_matches) * 0.2),
        })
        logger.debug("Detected %d distinct years", len(year_matches))

    # --- Numeric density ---
    num_matches = NUMBER_PATTERN.findall(text)
    word_count = len(text.split())
    if word_count > 0:
        numeric_ratio = len(num_matches) / word_count
        if numeric_ratio > 0.15:
            signals.append({
                "type": "numeric_density",
                "matches": num_matches[:10],  # Sample only
                "chart_hint": "BAR_CHART",
                "confidence": min(1.0, numeric_ratio * 2),
            })
            logger.debug(
                "High numeric density: %.2f (%d numbers in %d words)",
                numeric_ratio, len(num_matches), word_count
            )

    return signals


def detect_table_chart_potential(headers: list[str], rows: list[list[str]]) -> dict[str, Any] | None:
    """Analyze a parsed markdown table for chart-worthiness.

    Args:
        headers: Column header strings.
        rows: 2D list of cell strings.

    Returns:
        A signal dict if the table has chart potential, else None.
        Keys: "type", "numeric_columns", "chart_hint", "confidence"
    """
    if not headers or not rows:
        return None

    # Count numeric columns (columns where >50% of cells parse as numbers)
    numeric_col_indices: list[int] = []
    for col_idx in range(len(headers)):
        numeric_count = 0
        for row in rows:
            if col_idx < len(row):
                cell = row[col_idx].strip().replace(",", "").replace("$", "").replace("%", "")
                try:
                    float(cell)
                    numeric_count += 1
                except ValueError:
                    pass
        if len(rows) > 0 and numeric_count / len(rows) > 0.5:
            numeric_col_indices.append(col_idx)

    if not numeric_col_indices:
        return None

    # Detect year/time-series columns — treat them as labels, not numeric data
    year_col_indices: list[int] = []
    for col_idx in numeric_col_indices:
        is_year = True
        for row in rows:
            if col_idx < len(row):
                cell = row[col_idx].strip()
                try:
                    val = int(float(cell))
                    if not (1900 <= val <= 2100):
                        is_year = False
                        break
                except (ValueError, TypeError):
                    is_year = False
                    break
        if is_year:
            year_col_indices.append(col_idx)

    # Year columns act as labels, not data
    effective_numeric = [i for i in numeric_col_indices if i not in year_col_indices]
    if not effective_numeric and year_col_indices:
        # All numeric columns are years — not chart-worthy
        return None

    # Determine chart type based on structure
    label_columns = [i for i in range(len(headers)) if i not in effective_numeric]
    has_labels = len(label_columns) > 0
    num_data_cols = len(effective_numeric)
    has_time_axis = len(year_col_indices) > 0

    if has_time_axis and num_data_cols >= 1:
        chart_hint = "LINE_CHART"
    elif has_labels and num_data_cols == 1 and len(rows) <= 8:
        chart_hint = "PIE_CHART"
    elif has_labels and num_data_cols >= 1:
        chart_hint = "BAR_CHART"
    else:
        chart_hint = "BAR_CHART"

    result = {
        "type": "table_with_numerics",
        "numeric_columns": [headers[i] for i in effective_numeric],
        "label_column": headers[label_columns[0]] if label_columns else None,
        "chart_hint": chart_hint,
        "confidence": min(1.0, num_data_cols * 0.3 + len(rows) * 0.05),
        "row_count": len(rows),
    }
    logger.debug(
        "Table chart potential: %s (numeric cols: %s)",
        chart_hint, result["numeric_columns"]
    )
    return result


def has_any_data_signal(text: str) -> bool:
    """Quick check whether text contains any chart-worthy data.

    Args:
        text: Raw text to scan.

    Returns:
        True if at least one data signal is detected.
    """
    return len(detect_data_signals(text)) > 0
