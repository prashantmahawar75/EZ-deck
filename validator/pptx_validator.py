"""
validator/pptx_validator.py — Layer 5: Quality checks on generated .pptx files.

Runs integrity, structure, content coverage, and accessibility checks.
Returns a ValidationResult with a score and retry recommendations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pptx import Presentation
from pptx.util import Inches

from config import (
    SLIDE_COUNT_MIN,
    SLIDE_COUNT_MAX,
    SLIDE_COUNT_EXTENDED_MIN,
    SLIDE_COUNT_EXTENDED_MAX,
    VALIDATION_PASS_THRESHOLD,
    FONT_SIZE_MINIMUM,
    FONT_SIZE_FOOTNOTE,
    MAX_LINES_PER_SLIDE,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a generated presentation.

    Attributes:
        passed: Whether all critical checks passed.
        score: Quality score from 0.0 to 1.0.
        warnings: Non-critical issues found.
        errors: Critical issues found.
        retry_recommended: Whether a pipeline retry should be triggered.
        retry_hints: Guidance for the planner on what to fix.
    """
    passed: bool = True
    score: float = 1.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    retry_recommended: bool = False
    retry_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict.

        Returns:
            Dict representation.
        """
        return {
            "passed": self.passed,
            "score": round(self.score, 3),
            "warnings": self.warnings,
            "errors": self.errors,
            "retry_recommended": self.retry_recommended,
            "retry_hints": self.retry_hints,
        }


def validate_presentation(
    output_path: str,
    slide_plan: list[dict[str, Any]],
    ast_dict: dict[str, Any],
) -> ValidationResult:
    """Run all quality checks on a generated presentation.

    Args:
        output_path: Path to the generated .pptx file.
        slide_plan: The slide plan used to build the presentation.
        ast_dict: The original parsed AST dict.

    Returns:
        ValidationResult with aggregated checks.
    """
    result = ValidationResult()
    weights: list[tuple[float, float]] = []  # (weight, score) pairs

    # 1. File integrity
    prs = _check_file_integrity(output_path, result)
    weights.append((0.25, 1.0 if prs else 0.0))

    if prs is None:
        result.passed = False
        result.score = 0.0
        result.retry_recommended = True
        result.retry_hints.append("Generated file is corrupted, rebuild entirely")
        return result

    # 2. Slide count
    count_score = _check_slide_count(prs, result)
    weights.append((0.15, count_score))

    # 3. No empty slides
    empty_score = _check_no_empty_slides(prs, result)
    weights.append((0.15, empty_score))

    # 4. Text overflow detection
    overflow_score = _check_text_overflow(prs, result)
    weights.append((0.10, overflow_score))

    # 5. Source section coverage
    coverage_score = _check_source_coverage(slide_plan, ast_dict, result)
    weights.append((0.15, coverage_score))

    # 6. Chart rendering (if applicable)
    chart_score = _check_charts_rendered(prs, ast_dict, slide_plan, result)
    weights.append((0.10, chart_score))

    # 7. Master compliance
    master_score = _check_master_compliance(prs, result)
    weights.append((0.05, master_score))

    # 8. Accessibility (alt text + font size)
    a11y_score = _check_accessibility(prs, result)
    weights.append((0.10, a11y_score))

    # 9. Text density / 6x6 rule (no walls of text)
    density_score = _check_text_density(prs, result)
    weights.append((0.05, density_score))

    # Calculate weighted score
    total_weight = sum(w for w, _ in weights)
    if total_weight > 0:
        result.score = sum(w * s for w, s in weights) / total_weight
    else:
        result.score = 0.0

    # Determine pass/fail
    result.passed = len(result.errors) == 0 and result.score >= VALIDATION_PASS_THRESHOLD

    # Recommend retry if score is low
    if result.score < VALIDATION_PASS_THRESHOLD:
        result.retry_recommended = True

    logger.info(
        "Validation complete: score=%.2f, passed=%s, errors=%d, warnings=%d",
        result.score, result.passed, len(result.errors), len(result.warnings),
    )

    return result


def _check_file_integrity(path: str, result: ValidationResult) -> Presentation | None:
    """Check that the file opens as a valid .pptx.

    Args:
        path: Path to the .pptx file.
        result: ValidationResult to update.

    Returns:
        Presentation object if valid, None otherwise.
    """
    try:
        prs = Presentation(path)
        logger.debug("File integrity check passed: %s", path)
        return prs
    except Exception as exc:
        result.errors.append(f"File integrity FAIL: {exc}")
        logger.error("File integrity failed: %s", exc)
        return None


def _check_slide_count(prs: Presentation, result: ValidationResult) -> float:
    """Check that slide count is within acceptable range.

    Args:
        prs: Presentation object.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    count = len(prs.slides)

    if SLIDE_COUNT_MIN <= count <= SLIDE_COUNT_MAX:
        logger.debug("Slide count check passed: %d", count)
        return 1.0

    if SLIDE_COUNT_EXTENDED_MIN <= count <= SLIDE_COUNT_EXTENDED_MAX:
        result.warnings.append(
            f"Slide count {count} is outside ideal range [{SLIDE_COUNT_MIN}-{SLIDE_COUNT_MAX}] "
            f"but within extended range"
        )
        return 0.7

    result.errors.append(f"Slide count {count} is outside acceptable range")
    result.retry_hints.append(
        f"Adjust slide count to be between {SLIDE_COUNT_MIN} and {SLIDE_COUNT_MAX}"
    )
    return 0.3


def _check_no_empty_slides(prs: Presentation, result: ValidationResult) -> float:
    """Check that no slides are completely empty.

    Args:
        prs: Presentation object.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    empty_count = 0
    total = len(prs.slides)

    for i, slide in enumerate(prs.slides):
        has_content = False
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text and text not in ("Click to add title", "Click to add text",
                                         "Click to add subtitle"):
                    has_content = True
                    break
            elif shape.shape_type is not None:
                has_content = True
                break

        if not has_content:
            empty_count += 1
            result.warnings.append(f"Slide {i + 1} appears to be empty")

    if total == 0:
        return 0.0

    score = (total - empty_count) / total
    if empty_count > 0:
        result.retry_hints.append(f"Remove or fill {empty_count} empty slides")

    return score


def _check_text_overflow(prs: Presentation, result: ValidationResult) -> float:
    """Check for potential text overflow in text frames.

    Uses a heuristic: if text length greatly exceeds the estimated capacity
    of the shape, flag as overflow.

    Args:
        prs: Presentation object.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    overflow_count = 0
    checked = 0

    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            tf = shape.text_frame
            total_text = tf.text

            # Estimate capacity: shape height in inches * ~3 lines per inch * ~50 chars per line
            shape_height_inches = shape.height / 914400 if shape.height else 1.0
            shape_width_inches = shape.width / 914400 if shape.width else 1.0
            estimated_chars = int(shape_height_inches * 3 * shape_width_inches * 8)

            checked += 1
            if len(total_text) > estimated_chars * 1.5 and len(total_text) > 100:
                overflow_count += 1

    if checked == 0:
        return 1.0

    if overflow_count > 0:
        result.warnings.append(
            f"Potential text overflow detected in {overflow_count} text frames"
        )

    return max(0.0, 1.0 - (overflow_count / max(checked, 1)))


def _check_source_coverage(
    slide_plan: list[dict[str, Any]],
    ast_dict: dict[str, Any],
    result: ValidationResult,
) -> float:
    """Check that all source sections are represented in the slide plan.

    Args:
        slide_plan: The slide plan.
        ast_dict: Original AST dict.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    ast_sections = set()
    for sec in ast_dict.get("sections", []):
        heading = sec.get("heading", "").strip()
        if heading:
            ast_sections.add(heading.lower())

    if not ast_sections:
        return 1.0

    covered = set()
    for slide in slide_plan:
        for src in slide.get("source_sections", []):
            covered.add(src.lower())

    uncovered = ast_sections - covered
    if uncovered:
        result.warnings.append(
            f"Source sections not covered in slides: {', '.join(list(uncovered)[:5])}"
        )
        result.retry_hints.append(
            f"Ensure these sections are included: {', '.join(list(uncovered)[:3])}"
        )

    coverage = len(covered & ast_sections) / len(ast_sections) if ast_sections else 1.0
    return coverage


def _check_charts_rendered(
    prs: Presentation,
    ast_dict: dict[str, Any],
    slide_plan: list[dict[str, Any]],
    result: ValidationResult,
) -> float:
    """Check that chart slides exist when numeric data was detected.

    Args:
        prs: Presentation object.
        ast_dict: Original AST dict.
        slide_plan: The slide plan.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    has_numeric = ast_dict.get("metadata", {}).get("has_numeric_data", False)
    if not has_numeric:
        return 1.0

    chart_types = {"BAR_CHART", "PIE_CHART", "LINE_CHART", "AREA_CHART", "STAT_HIGHLIGHT"}
    has_chart_slide = any(
        s.get("slide_type", "") in chart_types for s in slide_plan
    )

    if not has_chart_slide:
        result.warnings.append(
            "Document has numeric data but no chart/stat slides were created"
        )
        result.retry_hints.append(
            "Add at least one chart or stat_highlight slide for the numeric data"
        )
        return 0.5

    return 1.0


def _check_master_compliance(prs: Presentation, result: ValidationResult) -> float:
    """Check that the slide master is properly attached and not corrupted.

    Args:
        prs: Presentation object.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    try:
        masters = list(prs.slide_masters)
        if not masters:
            result.errors.append("No slide master found in the presentation")
            return 0.0

        # Check that master has at least one layout
        layouts = list(masters[0].slide_layouts)
        if not layouts:
            result.warnings.append("Slide master has no layouts")
            return 0.5

        return 1.0

    except Exception as exc:
        result.errors.append(f"Slide master check failed: {exc}")
        return 0.0


def _check_accessibility(prs: Presentation, result: ValidationResult) -> float:
    """Check accessibility features: alt-text on images, etc.

    Args:
        prs: Presentation object.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    images_total = 0
    images_with_alt = 0
    small_text_count = 0

    for slide in prs.slides:
        for shape in slide.shapes:
            # Check images for alt text
            if shape.shape_type and shape.shape_type == 13:  # Picture
                images_total += 1
                try:
                    for elem in shape._element.iter():
                        if elem.tag.endswith("}cNvPr"):
                            descr = elem.get("descr", "")
                            if descr.strip():
                                images_with_alt += 1
                            break
                except Exception:
                    pass

            # Check for very small text (below global minimum)
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.font.size and run.font.size < FONT_SIZE_MINIMUM * 12700:  # Convert pt to emu
                            small_text_count += 1

    score = 1.0

    if images_total > 0:
        alt_ratio = images_with_alt / images_total
        if alt_ratio < 1.0:
            result.warnings.append(
                f"Only {images_with_alt}/{images_total} images have alt-text"
            )
            score -= (1.0 - alt_ratio) * 0.3

    if small_text_count > 3:
        result.warnings.append(
            f"Found {small_text_count} text runs with very small font size"
        )
        score -= 0.1

    return max(0.0, score)


def _check_text_density(prs: Presentation, result: ValidationResult) -> float:
    """Check text density per slide (6x6 / 7x7 rule).

    Counts paragraph lines per content text frame. If any slide has
    more than MAX_LINES_PER_SLIDE text paragraphs in a single frame,
    flag it as too dense ("wall of text").

    Args:
        prs: Presentation object.
        result: ValidationResult to update.

    Returns:
        Score from 0.0 to 1.0.
    """
    dense_slides = 0
    total = len(prs.slides)

    for i, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            tf = shape.text_frame
            # Count non-empty paragraphs (text lines)
            line_count = sum(
                1 for p in tf.paragraphs if p.text.strip()
            )
            if line_count > MAX_LINES_PER_SLIDE:
                dense_slides += 1
                result.warnings.append(
                    f"Slide {i + 1} has {line_count} text lines in one frame "
                    f"(max {MAX_LINES_PER_SLIDE} per 7x7 rule)"
                )
                break  # One dense frame is enough to flag the slide

    if total == 0:
        return 1.0

    return max(0.0, 1.0 - (dense_slides / total))
