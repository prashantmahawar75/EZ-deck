"""
parser/insight_engine.py — Data insight generation from parsed AST.

Takes structured numeric data (tables, lists with numbers) and produces
human-readable business insights: growth rates, inflection points,
rankings, share analysis, and trend summaries.

These insights feed into EXEC_SUMMARY, speaker notes, and KEY_TAKEAWAYS
so the presentation reads like a consultant built it — not a formatter.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

@dataclass
class Insight:
    """A single generated insight."""
    text: str
    category: str          # "growth", "ranking", "share", "inflection", "trend", "comparison"
    confidence: float      # 0.0–1.0
    source_section: str    # heading of the section this came from
    icon_hint: str = "📊"  # emoji for KEY_TAKEAWAYS


@dataclass
class SectionInsights:
    """All insights derived from a single section."""
    heading: str
    insights: list[Insight] = field(default_factory=list)
    speaker_note_fragment: str = ""  # 2-3 sentence summary for speaker notes


@dataclass
class DocumentInsights:
    """Full insight analysis for the entire document."""
    sections: list[SectionInsights] = field(default_factory=list)
    executive_insights: list[str] = field(default_factory=list)   # Top insights for EXEC_SUMMARY
    key_metric: str | None = None                                  # Best single metric found
    takeaways: list[Insight] = field(default_factory=list)         # Top insights for KEY_TAKEAWAYS

    def get_section_insights(self, heading: str) -> SectionInsights | None:
        """Get insights for a specific section by heading."""
        heading_lower = heading.lower().strip()
        for si in self.sections:
            if si.heading.lower().strip() == heading_lower:
                return si
        return None

    def get_speaker_notes(self, heading: str) -> str:
        """Get speaker note fragment for a section."""
        si = self.get_section_insights(heading)
        return si.speaker_note_fragment if si else ""


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────

def generate_insights(ast_dict: dict[str, Any]) -> DocumentInsights:
    """Analyze the full AST and generate insights for every data section.

    Args:
        ast_dict: Parsed AST from md_parser.

    Returns:
        DocumentInsights with section-level and document-level insights.
    """
    doc = DocumentInsights()
    sections = ast_dict.get("sections", [])

    all_insights: list[Insight] = []

    for section in sections:
        heading = section.get("heading", "")
        blocks = section.get("blocks", [])
        si = SectionInsights(heading=heading)

        for block in blocks:
            if block["type"] == "table":
                table_insights = _analyze_table(
                    heading,
                    block.get("content", {}),
                    block.get("data_signals", []),
                )
                si.insights.extend(table_insights)

            elif block["type"] in ("bullet_list", "ordered_list"):
                list_insights = _analyze_list(
                    heading,
                    block.get("content", []),
                    block.get("data_signals", []),
                )
                si.insights.extend(list_insights)

        # Generate speaker notes from insights
        if si.insights:
            si.speaker_note_fragment = _build_speaker_notes(si.insights)
            all_insights.extend(si.insights)

        doc.sections.append(si)

    # Build document-level outputs
    _build_executive_insights(doc, all_insights)
    _build_takeaways(doc, all_insights)
    _find_key_metric(doc, all_insights, sections)

    logger.info(
        "Insight engine: %d sections analyzed, %d insights generated, %d exec insights",
        len(sections), len(all_insights), len(doc.executive_insights),
    )
    return doc


# ──────────────────────────────────────────────
# Table analysis
# ──────────────────────────────────────────────

def _analyze_table(
    heading: str,
    content: dict[str, Any],
    data_signals: list[dict[str, Any]],
) -> list[Insight]:
    """Extract insights from a table block."""
    headers = content.get("headers", [])
    rows = content.get("rows", [])
    if not headers or not rows:
        return []

    insights: list[Insight] = []

    # Parse the table into label→values structure
    parsed = _parse_table_numeric(headers, rows)
    if not parsed:
        return insights

    label_col, value_cols = parsed

    for col_name, values in value_cols.items():
        labels = [v[0] for v in values]
        nums = [v[1] for v in values]

        if len(nums) < 2:
            continue

        is_time = _is_time_series(labels)
        chart_hint = _get_chart_hint(data_signals)

        if is_time or chart_hint == "LINE_CHART":
            insights.extend(_time_series_insights(heading, col_name, labels, nums))
        elif chart_hint == "PIE_CHART" or _looks_like_share(headers, col_name):
            insights.extend(_share_insights(heading, col_name, labels, nums))
        else:
            insights.extend(_ranking_insights(heading, col_name, labels, nums))

    return insights


def _parse_table_numeric(
    headers: list[str],
    rows: list[list[str]],
) -> tuple[str, dict[str, list[tuple[str, float]]]] | None:
    """Parse a table into label column + numeric value columns.

    Returns:
        (label_column_name, {value_col_name: [(label, number), ...]}) or None
    """
    if len(headers) < 2:
        return None

    # Detect which columns are numeric
    col_scores: dict[int, int] = {}
    for col_idx in range(len(headers)):
        numeric_count = 0
        is_year = True
        for row in rows:
            if col_idx < len(row):
                cell = _clean_numeric(row[col_idx])
                try:
                    val = float(cell)
                    numeric_count += 1
                    if not (1900 <= val <= 2100):
                        is_year = False
                except (ValueError, TypeError):
                    is_year = False
        col_scores[col_idx] = numeric_count
        # Year columns are labels, not values
        if is_year and numeric_count == len(rows):
            col_scores[col_idx] = 0

    # Find label column (least numeric, or first)
    label_idx = min(col_scores, key=col_scores.get)

    # Value columns are the rest with >50% numeric
    value_cols: dict[str, list[tuple[str, float]]] = {}
    for col_idx, count in col_scores.items():
        if col_idx == label_idx:
            continue
        if count / max(len(rows), 1) < 0.5:
            continue

        pairs: list[tuple[str, float]] = []
        for row in rows:
            if label_idx < len(row) and col_idx < len(row):
                try:
                    num = float(_clean_numeric(row[col_idx]))
                    pairs.append((row[label_idx].strip(), num))
                except (ValueError, TypeError):
                    continue

        if pairs:
            value_cols[headers[col_idx]] = pairs

    if not value_cols:
        return None

    return headers[label_idx], value_cols


# ──────────────────────────────────────────────
# Time-series insights
# ──────────────────────────────────────────────

def _time_series_insights(
    heading: str,
    col_name: str,
    labels: list[str],
    values: list[float],
) -> list[Insight]:
    """Generate insights from time-series data."""
    insights: list[Insight] = []
    n = len(values)
    metric_name = _friendly_metric_name(col_name, heading)

    # Total growth
    if values[0] != 0:
        total_growth_pct = ((values[-1] - values[0]) / abs(values[0])) * 100
        direction = "grew" if total_growth_pct > 0 else "declined"
        insights.append(Insight(
            text=f"{metric_name} {direction} {abs(total_growth_pct):.0f}% from {labels[0]} to {labels[-1]} ({_fmt_num(values[0])} → {_fmt_num(values[-1])})",
            category="growth",
            confidence=0.95,
            source_section=heading,
            icon_hint="📈" if total_growth_pct > 0 else "📉",
        ))

    # Year-over-year growth rates
    yoy_rates: list[tuple[str, str, float]] = []
    for i in range(1, n):
        if values[i - 1] != 0:
            rate = ((values[i] - values[i - 1]) / abs(values[i - 1])) * 100
            yoy_rates.append((labels[i - 1], labels[i], rate))

    # Find inflection point (largest acceleration in growth rate)
    if len(yoy_rates) >= 2:
        max_rate_idx = max(range(len(yoy_rates)), key=lambda i: yoy_rates[i][2])
        max_rate = yoy_rates[max_rate_idx]
        if max_rate[2] > 30:  # Only flag significant jumps
            insights.append(Insight(
                text=f"Sharpest growth occurred {max_rate[0]}→{max_rate[1]} with {max_rate[2]:.0f}% increase",
                category="inflection",
                confidence=0.9,
                source_section=heading,
                icon_hint="🚀",
            ))

    # Acceleration/deceleration trend
    if len(yoy_rates) >= 3:
        recent_rates = [r[2] for r in yoy_rates[-3:]]
        if all(recent_rates[i] < recent_rates[i - 1] for i in range(1, len(recent_rates))):
            insights.append(Insight(
                text=f"{metric_name} growth is decelerating — rate slowed from {recent_rates[0]:.0f}% to {recent_rates[-1]:.0f}%",
                category="trend",
                confidence=0.85,
                source_section=heading,
                icon_hint="⚠️",
            ))
        elif all(recent_rates[i] > recent_rates[i - 1] for i in range(1, len(recent_rates))):
            insights.append(Insight(
                text=f"{metric_name} growth is accelerating — rate increased from {recent_rates[0]:.0f}% to {recent_rates[-1]:.0f}%",
                category="trend",
                confidence=0.85,
                source_section=heading,
                icon_hint="🔥",
            ))

    # Latest value context
    if n >= 2 and values[-1] > values[-2]:
        latest_jump = ((values[-1] - values[-2]) / abs(values[-2])) * 100 if values[-2] != 0 else 0
        if latest_jump > 20:
            insights.append(Insight(
                text=f"Most recent period ({labels[-1]}): {metric_name} reached {_fmt_num(values[-1])}, up {latest_jump:.0f}% from {labels[-2]}",
                category="growth",
                confidence=0.8,
                source_section=heading,
                icon_hint="📊",
            ))

    return insights


# ──────────────────────────────────────────────
# Share/distribution insights
# ──────────────────────────────────────────────

def _share_insights(
    heading: str,
    col_name: str,
    labels: list[str],
    values: list[float],
) -> list[Insight]:
    """Generate insights from share/distribution data."""
    insights: list[Insight] = []
    total = sum(values)
    if total == 0:
        return insights

    # Sort by value descending
    sorted_pairs = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)

    # Leader insight
    leader = sorted_pairs[0]
    leader_pct = (leader[1] / total) * 100
    insights.append(Insight(
        text=f"{leader[0]} leads with {leader_pct:.0f}% share ({_fmt_num(leader[1])})",
        category="ranking",
        confidence=0.95,
        source_section=heading,
        icon_hint="🏆",
    ))

    # Concentration — top 2 combined
    if len(sorted_pairs) >= 2:
        top2_val = sorted_pairs[0][1] + sorted_pairs[1][1]
        top2_pct = (top2_val / total) * 100
        if top2_pct >= 60:
            insights.append(Insight(
                text=f"Top 2 ({sorted_pairs[0][0]} + {sorted_pairs[1][0]}) control {top2_pct:.0f}% of total",
                category="share",
                confidence=0.9,
                source_section=heading,
                icon_hint="📊",
            ))

    # Gap between #1 and #2
    if len(sorted_pairs) >= 2:
        gap = sorted_pairs[0][1] - sorted_pairs[1][1]
        if sorted_pairs[1][1] > 0:
            gap_pct = (gap / sorted_pairs[1][1]) * 100
            if gap_pct > 20:
                insights.append(Insight(
                    text=f"{sorted_pairs[0][0]} leads {sorted_pairs[1][0]} by {gap_pct:.0f}% ({_fmt_num(gap)} difference)",
                    category="comparison",
                    confidence=0.85,
                    source_section=heading,
                    icon_hint="⚡",
                ))

    # Tail — smallest entry
    if len(sorted_pairs) >= 3:
        tail = sorted_pairs[-1]
        tail_pct = (tail[1] / total) * 100
        if tail_pct < 10:
            insights.append(Insight(
                text=f"{tail[0]} represents only {tail_pct:.0f}% — smallest segment",
                category="share",
                confidence=0.75,
                source_section=heading,
                icon_hint="📉",
            ))

    return insights


# ──────────────────────────────────────────────
# Ranking/comparison insights
# ──────────────────────────────────────────────

def _ranking_insights(
    heading: str,
    col_name: str,
    labels: list[str],
    values: list[float],
) -> list[Insight]:
    """Generate insights from category-comparison data."""
    insights: list[Insight] = []
    metric_name = _friendly_metric_name(col_name, heading)

    sorted_pairs = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)

    # Top performer
    top = sorted_pairs[0]
    insights.append(Insight(
        text=f"{top[0]} leads in {metric_name} at {_fmt_num(top[1])}",
        category="ranking",
        confidence=0.9,
        source_section=heading,
        icon_hint="🏆",
    ))

    # Range
    if len(sorted_pairs) >= 2:
        bottom = sorted_pairs[-1]
        if bottom[1] > 0:
            multiple = top[1] / bottom[1]
            if multiple >= 2:
                insights.append(Insight(
                    text=f"{top[0]} outperforms {bottom[0]} by {multiple:.1f}x ({_fmt_num(top[1])} vs {_fmt_num(bottom[1])})",
                    category="comparison",
                    confidence=0.85,
                    source_section=heading,
                    icon_hint="⚡",
                ))

    return insights


# ──────────────────────────────────────────────
# List analysis
# ──────────────────────────────────────────────

def _analyze_list(
    heading: str,
    content: list[Any],
    data_signals: list[dict[str, Any]],
) -> list[Insight]:
    """Extract insights from bullet/ordered lists with numeric data."""
    insights: list[Insight] = []

    # Try to parse label: value pairs from list items
    pairs: list[tuple[str, float]] = []
    for item in content:
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        match = re.match(r"^(.+?):\s*([\d,.]+)%?$", text.strip())
        if match:
            try:
                pairs.append((match.group(1).strip(), float(match.group(2).replace(",", ""))))
            except ValueError:
                continue

    if len(pairs) >= 2:
        labels = [p[0] for p in pairs]
        values = [p[1] for p in pairs]

        if _is_time_series(labels):
            insights.extend(_time_series_insights(heading, heading, labels, values))
        else:
            insights.extend(_ranking_insights(heading, heading, labels, values))

    return insights


# ──────────────────────────────────────────────
# Document-level builders
# ──────────────────────────────────────────────

def _build_executive_insights(doc: DocumentInsights, all_insights: list[Insight]) -> None:
    """Pick the top 3-4 insights for the executive summary slide."""
    # Sort by confidence, prefer diverse categories
    sorted_ins = sorted(all_insights, key=lambda i: i.confidence, reverse=True)

    seen_categories: set[str] = set()
    for ins in sorted_ins:
        if len(doc.executive_insights) >= 4:
            break
        # Prefer one per category for diversity
        if ins.category in seen_categories and len(doc.executive_insights) < 3:
            continue
        doc.executive_insights.append(ins.text)
        seen_categories.add(ins.category)

    # If we have fewer than 3, add remaining high-confidence ones
    for ins in sorted_ins:
        if len(doc.executive_insights) >= 4:
            break
        if ins.text not in doc.executive_insights:
            doc.executive_insights.append(ins.text)


def _build_takeaways(doc: DocumentInsights, all_insights: list[Insight]) -> None:
    """Pick the top 5 insights for the KEY_TAKEAWAYS slide."""
    sorted_ins = sorted(all_insights, key=lambda i: i.confidence, reverse=True)

    seen_sections: set[str] = set()
    for ins in sorted_ins:
        if len(doc.takeaways) >= 5:
            break
        # Prefer one per section for coverage
        if ins.source_section in seen_sections and len(doc.takeaways) < 4:
            continue
        doc.takeaways.append(ins)
        seen_sections.add(ins.source_section)

    # Fill remaining slots
    for ins in sorted_ins:
        if len(doc.takeaways) >= 5:
            break
        if ins not in doc.takeaways:
            doc.takeaways.append(ins)


def _find_key_metric(
    doc: DocumentInsights,
    all_insights: list[Insight],
    sections: list[dict[str, Any]],
) -> None:
    """Find the single best key metric for the EXEC_SUMMARY."""
    # Prefer growth insights with concrete numbers
    for ins in sorted(all_insights, key=lambda i: i.confidence, reverse=True):
        if ins.category == "growth" and "grew" in ins.text:
            # Extract a compact version: "567% growth in X (2018→2023)"
            doc.key_metric = ins.text
            return

    # Fallback: look for currency/percentage in raw text
    for section in sections:
        for block in section.get("blocks", []):
            for sig in block.get("data_signals", []):
                if sig.get("type") == "currency" and sig.get("matches"):
                    doc.key_metric = sig["matches"][0]
                    return


def _build_speaker_notes(insights: list[Insight]) -> str:
    """Build a 2-3 sentence speaker note fragment from insights."""
    if not insights:
        return ""
    sentences = []
    for ins in insights[:3]:
        # Convert insight to natural speech
        text = ins.text
        if not text.endswith("."):
            text += "."
        sentences.append(text)
    return " ".join(sentences)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _clean_numeric(cell: str) -> str:
    """Strip currency symbols, commas, percent signs from a cell."""
    return cell.strip().replace(",", "").replace("$", "").replace("%", "").replace("€", "").replace("£", "").replace("+", "")


def _is_time_series(labels: list[str]) -> bool:
    """Check if labels look like a chronological sequence (years, quarters)."""
    year_count = 0
    for label in labels:
        label = label.strip()
        try:
            val = int(float(label))
            if 1900 <= val <= 2100:
                year_count += 1
        except (ValueError, TypeError):
            if re.match(r"^Q[1-4]\s*\d{4}$", label, re.IGNORECASE):
                year_count += 1
    return year_count >= len(labels) * 0.5


def _looks_like_share(headers: list[str], col_name: str) -> bool:
    """Check if a column looks like share/percentage data."""
    lower = col_name.lower()
    return any(kw in lower for kw in ("share", "%", "percent", "proportion", "distribution"))


def _get_chart_hint(data_signals: list[dict[str, Any]]) -> str:
    """Get the chart_hint from data signals if available."""
    for sig in data_signals:
        if sig.get("chart_hint"):
            return sig["chart_hint"]
    return ""


def _friendly_metric_name(col_name: str, heading: str) -> str:
    """Make a metric name human-friendly for insights."""
    # If column name is generic, use the heading
    generic = {"value", "amount", "count", "number", "total", "data"}
    if col_name.lower().strip() in generic:
        return heading
    return col_name


def _fmt_num(value: float) -> str:
    """Format a number for display in insights."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 10_000:
        return f"{value / 1_000:.0f}K"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    elif value == int(value):
        return str(int(value))
    else:
        return f"{value:.1f}"
