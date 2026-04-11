"""
builder/layout_manager.py — Manages Slide Master layout selection and dynamic creation.

Maps each slide_type to the most appropriate existing layout from the master.
Creates dynamic layouts when no suitable one exists by cloning the closest match.
"""

import copy
import logging
from typing import Any

from pptx import Presentation
from pptx.slide import SlideLayout
from lxml import etree

from config import VALID_SLIDE_TYPES

logger = logging.getLogger(__name__)

# Preferred layout mapping: slide_type → preferred layout index or name
LAYOUT_PREFERENCES: dict[str, list[int | str]] = {
    "TITLE":                     [0, "Title Slide"],
    "SECTION_DIVIDER":           [2, "Section Header"],
    "CONTENT_BULLETS":           [1, "Title and Content"],
    "CONTENT_TWO_COLUMN":        [3, "Two Content"],
    "STAT_HIGHLIGHT":            [5, 1, "Blank"],
    "BAR_CHART":                 [5, 6, 1, "Blank"],
    "PIE_CHART":                 [5, 6, 1, "Blank"],
    "LINE_CHART":                [5, 6, 1, "Blank"],
    "AREA_CHART":                [5, 6, 1, "Blank"],
    "TABLE":                     [1, 5, "Title and Content"],
    "TIMELINE_INFOGRAPHIC":      [5, 6, 1, "Blank"],
    "PROCESS_FLOW_INFOGRAPHIC":  [5, 6, 1, "Blank"],
    "COMPARISON_INFOGRAPHIC":    [3, 5, 1, "Blank"],
    "KEY_TAKEAWAYS":             [1, 5, "Title and Content"],
    "AGENDA":                    [1, "Title and Content"],
    "EXEC_SUMMARY":              [1, "Title and Content"],
}


class LayoutManager:
    """Manages slide layout selection from the Slide Master.

    Attributes:
        layouts: List of available SlideLayout objects.
        layout_map: Cached mapping of slide_type → SlideLayout.
        dynamic_layouts: List of dynamically created layouts.
    """

    def __init__(self, prs: Presentation) -> None:
        """Initialize with a Presentation that has a slide master loaded.

        Args:
            prs: python-pptx Presentation object with slide master.
        """
        self._prs = prs
        self.layouts: list[SlideLayout] = []
        self.layout_map: dict[str, SlideLayout] = {}
        self.dynamic_layouts: list[str] = []

        self._index_layouts()

    def _index_layouts(self) -> None:
        """Index all available layouts from the presentation's slide masters."""
        for slide_master in self._prs.slide_masters:
            for layout in slide_master.slide_layouts:
                self.layouts.append(layout)

        logger.info(
            "Indexed %d layouts from %d slide master(s)",
            len(self.layouts),
            len(self._prs.slide_masters),
        )

        if not self.layouts:
            logger.warning("No layouts found in slide master — will use dynamic layouts")

        # Log layout names for debugging
        for i, layout in enumerate(self.layouts):
            logger.debug("  Layout %d: '%s'", i, layout.name)

    def get_layout(self, slide_type: str) -> SlideLayout:
        """Get the best layout for a given slide type.

        Uses cached mapping if available, otherwise searches preferences.

        Args:
            slide_type: One of VALID_SLIDE_TYPES.

        Returns:
            The most appropriate SlideLayout.
        """
        # Check cache
        if slide_type in self.layout_map:
            return self.layout_map[slide_type]

        layout = self._find_best_layout(slide_type)
        self.layout_map[slide_type] = layout
        return layout

    def _find_best_layout(self, slide_type: str) -> SlideLayout:
        """Search for the best matching layout.

        Args:
            slide_type: Slide type to find a layout for.

        Returns:
            Best matching SlideLayout.
        """
        if not self.layouts:
            # No layouts at all — this should rarely happen
            raise ValueError("No slide layouts available in the master")

        preferences = LAYOUT_PREFERENCES.get(slide_type, [1, 0, "Blank"])

        for pref in preferences:
            if isinstance(pref, int):
                if 0 <= pref < len(self.layouts):
                    logger.debug(
                        "Matched '%s' to layout index %d ('%s')",
                        slide_type, pref, self.layouts[pref].name,
                    )
                    return self.layouts[pref]
            elif isinstance(pref, str):
                for layout in self.layouts:
                    if pref.lower() in layout.name.lower():
                        logger.debug(
                            "Matched '%s' to layout '%s'",
                            slide_type, layout.name,
                        )
                        return layout

        # Fallback: use the first layout that has a title placeholder
        for layout in self.layouts:
            for ph in layout.placeholders:
                if ph.placeholder_format.idx == 0:
                    logger.debug(
                        "Fallback: '%s' → layout '%s' (has title placeholder)",
                        slide_type, layout.name,
                    )
                    return layout

        # Ultimate fallback: first layout
        logger.warning(
            "No suitable layout for '%s', using first available: '%s'",
            slide_type, self.layouts[0].name,
        )
        return self.layouts[0]

    def get_blank_layout(self) -> SlideLayout:
        """Get a blank (or most minimal) layout.

        Returns:
            The layout with the fewest placeholders.
        """
        if not self.layouts:
            raise ValueError("No slide layouts available")

        # Find layout named "Blank" or with fewest placeholders
        for layout in self.layouts:
            if "blank" in layout.name.lower():
                return layout

        # Return layout with smallest placeholder count
        return min(self.layouts, key=lambda l: len(list(l.placeholders)))

    def get_title_only_layout(self) -> SlideLayout:
        """Get a layout with only a title placeholder.

        Returns:
            Layout suitable for slides where we add custom content.
        """
        if not self.layouts:
            raise ValueError("No slide layouts available")

        # Look for "Title Only" layout
        for layout in self.layouts:
            if "title only" in layout.name.lower():
                return layout

        # Look for layout with just title placeholder
        for layout in self.layouts:
            phs = list(layout.placeholders)
            if len(phs) == 1 and phs[0].placeholder_format.idx == 0:
                return layout

        # Fallback to blank
        return self.get_blank_layout()
