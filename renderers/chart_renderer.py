"""
renderers/chart_renderer.py — Renders bar, pie, line, and area charts via matplotlib.

All charts use a custom style derived from the Slide Master palette.
Never uses default matplotlib colors. Outputs high-DPI transparent PNGs.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from config import CHART_DPI, CHART_FIGURE_WIDTH, CHART_FIGURE_HEIGHT

logger = logging.getLogger(__name__)

# Default palette — overridden by style_constants when master is loaded
DEFAULT_PALETTE = [
    "#2E86AB",  # Steel blue
    "#A23B72",  # Mulberry
    "#F18F01",  # Tangerine
    "#C73E1D",  # Vermilion
    "#3B1F2B",  # Dark purple
    "#44BBA4",  # Mint
    "#E94F37",  # Coral red
    "#393E41",  # Charcoal
]

DEFAULT_FONT_FAMILY = "Calibri"


def _setup_style(palette: list[str] | None = None, font_family: str | None = None) -> tuple[list[str], str]:
    """Configure matplotlib style for presentation charts.

    Args:
        palette: Color palette from the Slide Master.
        font_family: Font family from the Slide Master.

    Returns:
        Tuple of (palette, font_family) to use.
    """
    colors = palette or DEFAULT_PALETTE
    font = font_family or DEFAULT_FONT_FAMILY

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [font, "Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 12,
        "axes.labelsize": 13,
        "axes.titlesize": 16,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
    })

    return colors, font


def _cycle_color(palette: list[str], index: int) -> str:
    """Get a color from the palette, cycling if index exceeds length.

    Args:
        palette: Color palette list.
        index: Color index.

    Returns:
        Hex color string.
    """
    return palette[index % len(palette)]


def render_bar_chart(
    series: list[dict[str, Any]],
    x_label: str = "",
    y_label: str = "",
    title: str = "",
    palette: list[str] | None = None,
    font_family: str | None = None,
) -> io.BytesIO:
    """Render a bar chart as a PNG image in memory.

    Args:
        series: List of dicts with "name" and "values" (list of [label, number]).
        x_label: X-axis label.
        y_label: Y-axis label.
        title: Chart title.
        palette: Optional color palette override.
        font_family: Optional font family override.

    Returns:
        BytesIO containing PNG image data.
    """
    colors, font = _setup_style(palette, font_family)

    fig, ax = plt.subplots(figsize=(CHART_FIGURE_WIDTH, CHART_FIGURE_HEIGHT))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    num_series = len(series)
    all_labels: list[str] = []

    for s in series:
        values = s.get("values", [])
        for item in values:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                label = str(item[0])
                if label not in all_labels:
                    all_labels.append(label)

    if not all_labels:
        logger.warning("Bar chart has no data labels, using defaults")
        all_labels = ["Item"]

    import numpy as np
    x = np.arange(len(all_labels))
    bar_width = 0.8 / max(num_series, 1)

    for idx, s in enumerate(series):
        values_map: dict[str, float] = {}
        for item in s.get("values", []):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    values_map[str(item[0])] = float(item[1])
                except (ValueError, TypeError):
                    values_map[str(item[0])] = 0.0

        y_values = [values_map.get(label, 0.0) for label in all_labels]
        offset = (idx - num_series / 2 + 0.5) * bar_width
        bars = ax.bar(
            x + offset, y_values, bar_width,
            label=s.get("name", f"Series {idx + 1}"),
            color=_cycle_color(colors, idx),
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
        )

        # Add value labels on bars
        for bar, val in zip(bars, y_values):
            if val != 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{val:,.1f}" if isinstance(val, float) and val != int(val) else f"{int(val):,}",
                    ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color="#333333",
                )

    ax.set_xticks(x)
    ax.set_xticklabels(all_labels, rotation=30 if len(all_labels) > 5 else 0, ha="right" if len(all_labels) > 5 else "center")

    if x_label:
        ax.set_xlabel(x_label, fontweight="bold")
    if y_label:
        ax.set_ylabel(y_label, fontweight="bold")
    if title:
        ax.set_title(title, fontweight="bold", pad=15)

    # Style: remove top and right spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")

    # Grid
    ax.yaxis.grid(True, color="#E0E0E0", alpha=0.5, zorder=0)
    ax.xaxis.grid(False)

    if num_series > 1:
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            frameon=False,
        )

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=CHART_DPI, transparent=True, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    logger.info("Rendered bar chart: '%s' with %d series", title, num_series)
    return buf


def render_pie_chart(
    slices: list[dict[str, Any]],
    title: str = "",
    palette: list[str] | None = None,
    font_family: str | None = None,
) -> io.BytesIO:
    """Render a pie chart as a PNG image in memory.

    Args:
        slices: List of dicts with "label" and "value".
        title: Chart title.
        palette: Optional color palette override.
        font_family: Optional font family override.

    Returns:
        BytesIO containing PNG image data.
    """
    colors, font = _setup_style(palette, font_family)

    fig, ax = plt.subplots(figsize=(CHART_FIGURE_WIDTH, CHART_FIGURE_HEIGHT))
    fig.patch.set_alpha(0)

    labels = [s.get("label", "?") for s in slices]
    values = []
    for s in slices:
        try:
            values.append(float(s.get("value", 0)))
        except (ValueError, TypeError):
            values.append(0)

    pie_colors = [_cycle_color(colors, i) for i in range(len(slices))]

    # Explode the largest slice slightly
    max_idx = values.index(max(values)) if values else 0
    explode = [0.05 if i == max_idx else 0 for i in range(len(values))]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        colors=pie_colors,
        explode=explode,
        startangle=90,
        pctdistance=0.75,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )

    for text in texts:
        text.set_fontsize(11)
        text.set_color("#333333")
    for autotext in autotexts:
        autotext.set_fontsize(10)
        autotext.set_fontweight("bold")
        autotext.set_color("white")

    if title:
        ax.set_title(title, fontweight="bold", pad=20, fontsize=16)

    ax.axis("equal")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=CHART_DPI, transparent=True, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    logger.info("Rendered pie chart: '%s' with %d slices", title, len(slices))
    return buf


def render_line_chart(
    series: list[dict[str, Any]],
    x_label: str = "",
    y_label: str = "",
    title: str = "",
    palette: list[str] | None = None,
    font_family: str | None = None,
) -> io.BytesIO:
    """Render a line chart as a PNG image in memory.

    Args:
        series: List of dicts with "name" and "points" (list of [x, y]).
        x_label: X-axis label.
        y_label: Y-axis label.
        title: Chart title.
        palette: Optional color palette override.
        font_family: Optional font family override.

    Returns:
        BytesIO containing PNG image data.
    """
    colors, font = _setup_style(palette, font_family)

    fig, ax = plt.subplots(figsize=(CHART_FIGURE_WIDTH, CHART_FIGURE_HEIGHT))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    for idx, s in enumerate(series):
        points = s.get("points", [])
        x_vals = []
        y_vals = []
        for pt in points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    x_vals.append(float(pt[0]) if _is_numeric(pt[0]) else pt[0])
                    y_vals.append(float(pt[1]))
                except (ValueError, TypeError):
                    continue

        color = _cycle_color(colors, idx)
        ax.plot(
            x_vals, y_vals,
            marker="o",
            markersize=6,
            linewidth=2.5,
            color=color,
            label=s.get("name", f"Series {idx + 1}"),
            zorder=3,
        )

        # Add data labels
        for x, y in zip(x_vals, y_vals):
            ax.annotate(
                f"{y:,.1f}" if isinstance(y, float) and y != int(y) else f"{int(y):,}",
                (x, y),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=9,
                color=color,
                fontweight="bold",
            )

    if x_label:
        ax.set_xlabel(x_label, fontweight="bold")
    if y_label:
        ax.set_ylabel(y_label, fontweight="bold")
    if title:
        ax.set_title(title, fontweight="bold", pad=15)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")

    ax.yaxis.grid(True, color="#E0E0E0", alpha=0.5, zorder=0)
    ax.xaxis.grid(False)

    if len(series) > 1:
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            frameon=False,
        )

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=CHART_DPI, transparent=True, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    logger.info("Rendered line chart: '%s' with %d series", title, len(series))
    return buf


def render_area_chart(
    series: list[dict[str, Any]],
    x_label: str = "",
    y_label: str = "",
    title: str = "",
    palette: list[str] | None = None,
    font_family: str | None = None,
) -> io.BytesIO:
    """Render an area chart as a PNG image in memory.

    Args:
        series: List of dicts with "name" and "points" (list of [x, y]).
        x_label: X-axis label.
        y_label: Y-axis label.
        title: Chart title.
        palette: Optional color palette override.
        font_family: Optional font family override.

    Returns:
        BytesIO containing PNG image data.
    """
    colors, font = _setup_style(palette, font_family)

    fig, ax = plt.subplots(figsize=(CHART_FIGURE_WIDTH, CHART_FIGURE_HEIGHT))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    for idx, s in enumerate(series):
        points = s.get("points", [])
        x_vals = []
        y_vals = []
        for pt in points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    x_vals.append(float(pt[0]) if _is_numeric(pt[0]) else pt[0])
                    y_vals.append(float(pt[1]))
                except (ValueError, TypeError):
                    continue

        color = _cycle_color(colors, idx)
        ax.fill_between(x_vals, y_vals, alpha=0.3, color=color, zorder=2)
        ax.plot(
            x_vals, y_vals,
            linewidth=2.5,
            color=color,
            label=s.get("name", f"Series {idx + 1}"),
            zorder=3,
        )

    if x_label:
        ax.set_xlabel(x_label, fontweight="bold")
    if y_label:
        ax.set_ylabel(y_label, fontweight="bold")
    if title:
        ax.set_title(title, fontweight="bold", pad=15)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")

    ax.yaxis.grid(True, color="#E0E0E0", alpha=0.5, zorder=0)
    ax.xaxis.grid(False)

    if len(series) > 1:
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            frameon=False,
        )

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=CHART_DPI, transparent=True, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    logger.info("Rendered area chart: '%s' with %d series", title, len(series))
    return buf


def _is_numeric(value: Any) -> bool:
    """Check if a value can be interpreted as a number.

    Args:
        value: Any value to check.

    Returns:
        True if value is numeric.
    """
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False
