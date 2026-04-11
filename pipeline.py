"""
pipeline.py — Orchestrator: wires all 5 layers of the MD-to-PPTX pipeline.

Manages the full flow: parse → plan → build → validate → retry.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MASTER_PATH,
    SLIDE_COUNT_DEFAULT,
    MAX_RETRY_COUNT,
    PlannerError,
    BuildError,
)
from parser.md_parser import parse_markdown
from planner.ai_planner import plan_slides
from planner.fallback_planner import plan_slides_fallback
from builder.pptx_builder import PPTXBuilder
from validator.pptx_validator import validate_presentation, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a full pipeline run.

    Attributes:
        output_path: Path to the generated .pptx file.
        slide_count: Number of slides in the output.
        validation: ValidationResult from the QA validator.
        timing: Dict with timing info in milliseconds.
        warnings: Aggregated warnings from all stages.
    """
    output_path: str = ""
    slide_count: int = 0
    validation: ValidationResult = field(default_factory=ValidationResult)
    timing: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict.

        Returns:
            Dict representation.
        """
        return {
            "output_path": self.output_path,
            "slide_count": self.slide_count,
            "validation": self.validation.to_dict(),
            "timing": self.timing,
            "warnings": self.warnings,
        }


class MarkdownToPPTXPipeline:
    """Orchestrates the full markdown-to-presentation pipeline.

    Wires together the parser, planner, builder, and validator with
    automatic retry on validation failure.

    Attributes:
        master_path: Path to the slide master template.
        output_dir: Directory for generated files.
        target_slides: Target number of slides.
        use_ai: Whether to use AI planner (False = fallback only).
    """

    def __init__(
        self,
        master_path: str,
        output_dir: str | None = None,
        target_slides: int = SLIDE_COUNT_DEFAULT,
        use_ai: bool = True,
    ) -> None:
        """Initialize the pipeline.

        Args:
            master_path: Path to slide_master.pptx.
            output_dir: Output directory (default: ./outputs).
            target_slides: Target slide count (10-15).
            use_ai: Use AI planner if True, rule-based fallback if False.
        """
        self.master_path = master_path
        self.output_dir = output_dir or str(DEFAULT_OUTPUT_DIR)
        self.target_slides = target_slides
        self.use_ai = use_ai

    def run(self, md_path: str) -> PipelineResult:
        """Run the full pipeline.

        Args:
            md_path: Path to the markdown file.

        Returns:
            PipelineResult with output path, validation, and timing.
        """
        result = PipelineResult()
        pipeline_start = time.time()

        # ── Step 1: Validate input ──
        logger.info("=" * 60)
        logger.info("PIPELINE START: %s", md_path)
        logger.info("=" * 60)

        if not Path(md_path).exists():
            result.warnings.append(f"Input file not found: {md_path}")
            result.validation.passed = False
            result.validation.errors.append(f"Input file not found: {md_path}")
            return result

        if not Path(self.master_path).exists():
            result.warnings.append(f"Master template not found: {self.master_path}")
            result.validation.passed = False
            result.validation.errors.append(f"Master template not found: {self.master_path}")
            return result

        # ── Step 2: Parse markdown → AST ──
        parse_start = time.time()
        try:
            ast_dict = parse_markdown(md_path)
            logger.info(
                "Parsed: %d sections, %d words",
                len(ast_dict.get("sections", [])),
                ast_dict.get("metadata", {}).get("word_count", 0),
            )
        except Exception as exc:
            logger.error("Parse failed: %s", exc)
            result.validation.errors.append(f"Parse error: {exc}")
            result.validation.passed = False
            return result
        parse_ms = int((time.time() - parse_start) * 1000)

        # ── Step 3: Plan slides ──
        plan_start = time.time()
        slide_plan = self._plan_slides(ast_dict, result)
        plan_ms = int((time.time() - plan_start) * 1000)

        if not slide_plan:
            result.validation.errors.append("Failed to generate slide plan")
            result.validation.passed = False
            return result

        logger.info("Slide plan: %d slides", len(slide_plan))

        # ── Steps 4-6: Build, validate, retry loop ──
        retry_hints: list[str] = []
        output_path = ""

        for attempt in range(MAX_RETRY_COUNT + 1):
            if attempt > 0:
                logger.info("── RETRY %d/%d ──", attempt, MAX_RETRY_COUNT)
                # Re-plan with retry hints
                plan_start2 = time.time()
                slide_plan = self._plan_slides(ast_dict, result, retry_hints)
                plan_ms += int((time.time() - plan_start2) * 1000)

                if not slide_plan:
                    break

            # ── Step 4: Build PPTX ──
            build_start = time.time()
            try:
                output_filename = Path(md_path).stem + (
                    f"_v{attempt + 1}" if attempt > 0 else ""
                ) + ".pptx"

                builder = PPTXBuilder(self.master_path, self.output_dir)
                builder.initialize()
                output_path = builder.build(slide_plan, output_filename)

            except Exception as exc:
                logger.error("Build failed: %s", exc)
                result.warnings.append(f"Build error (attempt {attempt + 1}): {exc}")
                continue
            build_ms = int((time.time() - build_start) * 1000)

            # ── Step 5: Validate ──
            validation = validate_presentation(output_path, slide_plan, ast_dict)

            if validation.passed or attempt >= MAX_RETRY_COUNT:
                result.output_path = output_path
                result.slide_count = len(slide_plan)
                result.validation = validation
                result.timing = {
                    "parse_ms": parse_ms,
                    "plan_ms": plan_ms,
                    "build_ms": build_ms,
                    "total_ms": int((time.time() - pipeline_start) * 1000),
                }
                result.warnings.extend(validation.warnings)
                break

            # ── Step 6: Auto-retry ──
            retry_hints = validation.retry_hints
            result.warnings.append(
                f"Attempt {attempt + 1} validation score: {validation.score:.2f}"
            )

        if not result.output_path and output_path:
            result.output_path = output_path
            result.timing = {
                "parse_ms": parse_ms,
                "plan_ms": plan_ms,
                "build_ms": 0,
                "total_ms": int((time.time() - pipeline_start) * 1000),
            }

        logger.info("=" * 60)
        logger.info(
            "PIPELINE COMPLETE: %s (score: %.2f)",
            result.output_path, result.validation.score,
        )
        logger.info("=" * 60)

        return result

    def _plan_slides(
        self,
        ast_dict: dict[str, Any],
        result: PipelineResult,
        retry_hints: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a slide plan using AI or fallback.

        Args:
            ast_dict: Parsed AST dict.
            result: PipelineResult to update with warnings.
            retry_hints: Optional hints from previous validation.

        Returns:
            List of slide plan dicts.
        """
        slide_plan: list[dict[str, Any]] = []

        if self.use_ai:
            try:
                slide_plan = plan_slides(ast_dict, self.target_slides, retry_hints)
            except Exception as exc:
                logger.warning("AI planner error: %s — falling back", exc)
                result.warnings.append(f"AI planner fallback: {exc}")

        if not slide_plan:
            logger.info("Using rule-based fallback planner")
            try:
                slide_plan = plan_slides_fallback(ast_dict, self.target_slides)
            except Exception as exc:
                logger.error("Fallback planner also failed: %s", exc)
                result.warnings.append(f"Fallback planner error: {exc}")

        return slide_plan
