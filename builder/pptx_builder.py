"""
builder/pptx_builder.py — Layer 4: Assembles the final .pptx presentation.

The most critical module. Loads the Slide Master, extracts theme info,
and builds the complete presentation by iterating over the slide plan.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Emu

from builder.layout_manager import LayoutManager
from builder.slide_factory import create_slide
from builder.style_constants import MasterStyle, extract_master_style
from config import (
    SLIDE_WIDTH_INCHES,
    SLIDE_HEIGHT_INCHES,
    DEFAULT_OUTPUT_DIR,
    BuildError,
)

logger = logging.getLogger(__name__)


class PPTXBuilder:
    """Builds a .pptx file from a slide plan using a Slide Master.

    Attributes:
        master_path: Path to the slide master .pptx file.
        output_dir: Directory to write the output file.
        style: Extracted MasterStyle.
        prs: python-pptx Presentation object.
        layout_mgr: LayoutManager for layout selection.
    """

    def __init__(self, master_path: str, output_dir: str | None = None) -> None:
        """Initialize the builder.

        Args:
            master_path: Path to the slide_master.pptx template.
            output_dir: Directory for output files.
        """
        self.master_path = master_path
        self.output_dir = output_dir or str(DEFAULT_OUTPUT_DIR)
        self.style: MasterStyle | None = None
        self.prs: Presentation | None = None
        self.layout_mgr: LayoutManager | None = None

    def initialize(self) -> None:
        """Load the Slide Master and extract theme information.

        Raises:
            BuildError: If the master file cannot be loaded.
        """
        master = Path(self.master_path)
        if not master.exists():
            raise BuildError(f"Slide master not found: {self.master_path}")

        # Extract style before creating presentation
        logger.info("Extracting style from master: %s", self.master_path)
        self.style = extract_master_style(self.master_path)

        # Create presentation from master template
        try:
            self.prs = Presentation(self.master_path)
        except Exception as exc:
            raise BuildError(f"Failed to load slide master: {exc}") from exc

        # Remove any existing slides from the template
        # (python-pptx doesn't have a direct API, so we manipulate XML)
        self._remove_template_slides()

        # Set slide dimensions
        self.prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
        self.prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)

        # Initialize layout manager
        self.layout_mgr = LayoutManager(self.prs)

        logger.info(
            "Builder initialized: %d layouts, accent=%s, font=%s",
            len(self.layout_mgr.layouts),
            self.style.accent_color,
            self.style.font_name,
        )

    def build(
        self,
        slide_plan: list[dict[str, Any]],
        output_filename: str = "presentation.pptx",
    ) -> str:
        """Build the complete presentation from a slide plan.

        Args:
            slide_plan: List of slide plan dicts.
            output_filename: Name for the output file.

        Returns:
            Full path to the generated .pptx file.

        Raises:
            BuildError: If building fails.
        """
        if self.prs is None or self.layout_mgr is None or self.style is None:
            self.initialize()

        assert self.prs is not None
        assert self.layout_mgr is not None
        assert self.style is not None

        logger.info("Building presentation with %d slides", len(slide_plan))

        total_slides_created = 0
        for plan_item in slide_plan:
            try:
                created = create_slide(plan_item, self.prs, self.layout_mgr, self.style)
                total_slides_created += len(created)
            except Exception as exc:
                logger.error(
                    "Failed to create slide %d (%s): %s",
                    plan_item.get("slide_number", 0),
                    plan_item.get("slide_type", "?"),
                    exc,
                )

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, output_filename)

        try:
            self.prs.save(output_path)
            logger.info("Saved presentation to: %s (%d slides)", output_path, total_slides_created)
        except Exception as exc:
            raise BuildError(f"Failed to save presentation: {exc}") from exc

        return output_path

    def _remove_template_slides(self) -> None:
        """Remove any pre-existing slides from the template.

        The master .pptx may contain sample slides — we remove them
        to start with a clean deck.
        """
        if self.prs is None:
            return

        try:
            # python-pptx stores slides in the slide list part
            xml_slides = self.prs.slides._sldIdLst

            # Collect slide IDs to remove
            slide_ids = list(xml_slides)
            for sld_id in slide_ids:
                # Remove the relationship
                r_id = sld_id.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                if r_id:
                    try:
                        self.prs.part.drop_rel(r_id)
                    except Exception:
                        pass
                xml_slides.remove(sld_id)

            if slide_ids:
                logger.info("Removed %d template slides", len(slide_ids))

        except Exception as exc:
            logger.debug("Could not remove template slides: %s", exc)
