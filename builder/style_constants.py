"""
builder/style_constants.py — Master-derived colors, fonts, and spacing.

Extracts theme information from the Slide Master file and exposes it
as constants for renderers and the builder to consume.
"""

import logging
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from lxml import etree

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Default palette (used when master extraction fails)
# ──────────────────────────────────────────────
DEFAULT_ACCENT_COLOR = RGBColor(0x2E, 0x86, 0xAB)
DEFAULT_DARK_TEXT = RGBColor(0x1A, 0x1A, 0x2E)
DEFAULT_LIGHT_TEXT = RGBColor(0x55, 0x55, 0x55)
DEFAULT_BG_COLOR = RGBColor(0xFF, 0xFF, 0xFF)
DEFAULT_FONT_NAME = "Calibri"

DEFAULT_CHART_PALETTE = [
    "#2E86AB",
    "#A23B72",
    "#F18F01",
    "#C73E1D",
    "#3B1F2B",
    "#44BBA4",
    "#E94F37",
    "#393E41",
]


class MasterStyle:
    """Holds style information extracted from a Slide Master file.

    Attributes:
        accent_color: Primary accent color (RGBColor).
        accent_color_2: Secondary accent color (RGBColor).
        dark_text: Dark text color (RGBColor).
        light_text: Light text color (RGBColor).
        bg_color: Background color (RGBColor).
        font_name: Primary font family name.
        font_name_minor: Secondary/body font family name.
        chart_palette: List of hex color strings for charts.
    """

    def __init__(self) -> None:
        """Initialize with defaults."""
        self.accent_color: RGBColor = DEFAULT_ACCENT_COLOR
        self.accent_color_2: RGBColor = RGBColor(0xA2, 0x3B, 0x72)
        self.dark_text: RGBColor = DEFAULT_DARK_TEXT
        self.light_text: RGBColor = DEFAULT_LIGHT_TEXT
        self.bg_color: RGBColor = DEFAULT_BG_COLOR
        self.font_name: str = DEFAULT_FONT_NAME
        self.font_name_minor: str = DEFAULT_FONT_NAME
        self.chart_palette: list[str] = list(DEFAULT_CHART_PALETTE)


def extract_master_style(master_path: str) -> MasterStyle:
    """Extract theme colors and fonts from a Slide Master .pptx file.

    Args:
        master_path: Path to the slide_master.pptx file.

    Returns:
        MasterStyle object with extracted (or default) values.
    """
    style = MasterStyle()

    try:
        prs = Presentation(master_path)
    except Exception as exc:
        logger.warning("Failed to load master file '%s': %s. Using defaults.", master_path, exc)
        return style

    # Extract theme from slide master
    try:
        slide_master = prs.slide_masters[0]
        theme_element = slide_master.element.find(
            ".//{http://schemas.openxmlformats.org/drawingml/2006/main}theme"
        )

        # Try to get theme from the slide master's relationship
        _extract_theme_colors(prs, style)
        _extract_theme_fonts(prs, style)

    except Exception as exc:
        logger.warning("Theme extraction failed: %s. Using defaults.", exc)

    # Build chart palette from extracted colors
    style.chart_palette = _build_chart_palette(style)

    logger.info(
        "Master style: accent=%s, font=%s, palette_size=%d",
        style.accent_color, style.font_name, len(style.chart_palette),
    )
    return style


def _extract_theme_colors(prs: Any, style: MasterStyle) -> None:
    """Extract theme colors from the presentation's theme XML.

    Args:
        prs: python-pptx Presentation object.
        style: MasterStyle object to populate.
    """
    nsmap = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    try:
        slide_master = prs.slide_masters[0]
        # Access the theme through the slide master's part
        theme_part = None
        for rel in slide_master.part.rels.values():
            if "theme" in rel.reltype:
                theme_part = rel.target_part
                break

        if theme_part is None:
            logger.debug("No theme part found in slide master")
            return

        # python-pptx 0.6.x: Part may not have .element; parse from blob
        if hasattr(theme_part, 'element'):
            theme_xml = theme_part.element
        else:
            theme_xml = etree.fromstring(theme_part.blob)
        color_scheme = theme_xml.find(".//a:themeElements/a:clrScheme", nsmap)

        if color_scheme is None:
            logger.debug("No color scheme found in theme")
            return

        # Extract specific colors
        color_map = {
            "dk1": "dark_text",
            "lt1": "bg_color",
            "accent1": "accent_color",
            "accent2": "accent_color_2",
        }

        for xml_name, attr_name in color_map.items():
            color_elem = color_scheme.find(f"a:{xml_name}", nsmap)
            if color_elem is not None:
                # Try srgbClr first, then sysClr
                srgb = color_elem.find("a:srgbClr", nsmap)
                if srgb is not None:
                    hex_val = srgb.get("val", "")
                    if len(hex_val) == 6:
                        rgb = RGBColor(
                            int(hex_val[0:2], 16),
                            int(hex_val[2:4], 16),
                            int(hex_val[4:6], 16),
                        )
                        setattr(style, attr_name, rgb)
                        logger.debug("Extracted %s: #%s", attr_name, hex_val)
                else:
                    sys_clr = color_elem.find("a:sysClr", nsmap)
                    if sys_clr is not None:
                        last_clr = sys_clr.get("lastClr", "")
                        if len(last_clr) == 6:
                            rgb = RGBColor(
                                int(last_clr[0:2], 16),
                                int(last_clr[2:4], 16),
                                int(last_clr[4:6], 16),
                            )
                            setattr(style, attr_name, rgb)

        # Extract additional accent colors for chart palette
        accent_colors = []
        for i in range(1, 7):
            accent_elem = color_scheme.find(f"a:accent{i}", nsmap)
            if accent_elem is not None:
                srgb = accent_elem.find("a:srgbClr", nsmap)
                if srgb is not None:
                    hex_val = srgb.get("val", "")
                    if len(hex_val) == 6:
                        accent_colors.append(f"#{hex_val}")

        if accent_colors:
            style.chart_palette = accent_colors
            logger.info("Extracted %d accent colors for chart palette", len(accent_colors))

    except Exception as exc:
        logger.warning("Color extraction failed: %s", exc)


def _extract_theme_fonts(prs: Any, style: MasterStyle) -> None:
    """Extract theme fonts from the presentation's theme XML.

    Args:
        prs: python-pptx Presentation object.
        style: MasterStyle object to populate.
    """
    nsmap = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }

    try:
        slide_master = prs.slide_masters[0]
        theme_part = None
        for rel in slide_master.part.rels.values():
            if "theme" in rel.reltype:
                theme_part = rel.target_part
                break

        if theme_part is None:
            return

        # python-pptx 0.6.x: Part may not have .element; parse from blob
        if hasattr(theme_part, 'element'):
            theme_xml = theme_part.element
        else:
            theme_xml = etree.fromstring(theme_part.blob)
        font_scheme = theme_xml.find(".//a:themeElements/a:fontScheme", nsmap)

        if font_scheme is None:
            return

        # Major font (headings)
        major_font = font_scheme.find("a:majorFont/a:latin", nsmap)
        if major_font is not None:
            typeface = major_font.get("typeface", "")
            if typeface:
                style.font_name = typeface
                logger.debug("Major font: %s", typeface)

        # Minor font (body)
        minor_font = font_scheme.find("a:minorFont/a:latin", nsmap)
        if minor_font is not None:
            typeface = minor_font.get("typeface", "")
            if typeface:
                style.font_name_minor = typeface
                logger.debug("Minor font: %s", typeface)

    except Exception as exc:
        logger.warning("Font extraction failed: %s", exc)


def _build_chart_palette(style: MasterStyle) -> list[str]:
    """Build a complete chart palette from extracted style.

    Ensures at least 8 colors by extending with defaults.

    Args:
        style: MasterStyle with extracted colors.

    Returns:
        List of hex color strings.
    """
    palette = list(style.chart_palette)

    # Add defaults to reach minimum 8 colors
    for default_color in DEFAULT_CHART_PALETTE:
        if default_color not in palette:
            palette.append(default_color)
        if len(palette) >= 8:
            break

    return palette
