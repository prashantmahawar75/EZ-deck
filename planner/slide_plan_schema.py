"""
planner/slide_plan_schema.py — Pydantic models for slide plan validation.

Every slide plan from the AI planner is validated against these schemas.
Validation errors are fed back to the AI for self-healing retries.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

from config import VALID_SLIDE_TYPES, SLIDE_COUNT_MIN, SLIDE_COUNT_MAX


# ──────────────────────────────────────────────
# Content schemas by slide type
# ──────────────────────────────────────────────

class TitleContent(BaseModel):
    """Content for TITLE slides."""
    headline: str
    subheadline: str = ""
    presenter: Optional[str] = None


class AgendaItem(BaseModel):
    """Single agenda item."""
    number: int
    topic: str


class AgendaContent(BaseModel):
    """Content for AGENDA slides."""
    items: list[AgendaItem] = Field(min_length=1)


class ExecSummaryContent(BaseModel):
    """Content for EXEC_SUMMARY slides."""
    insights: list[str] = Field(min_length=1, max_length=4)
    key_metric: Optional[str] = None


class BulletItem(BaseModel):
    """A bullet point with optional sub-bullets."""
    text: str
    sub_bullets: Optional[list[str]] = None


class ContentBulletsContent(BaseModel):
    """Content for CONTENT_BULLETS slides."""
    bullets: list[BulletItem] = Field(min_length=1, max_length=7)


class ColumnContent(BaseModel):
    """One column of a two-column layout."""
    heading: str
    points: list[str] = Field(min_length=1)


class ContentTwoColumnContent(BaseModel):
    """Content for CONTENT_TWO_COLUMN slides."""
    left: ColumnContent
    right: ColumnContent


class StatItem(BaseModel):
    """A single stat for stat-highlight slides."""
    value: str
    label: str
    context: str = ""


class StatHighlightContent(BaseModel):
    """Content for STAT_HIGHLIGHT slides."""
    stats: list[StatItem] = Field(min_length=1, max_length=3)


class ChartSeries(BaseModel):
    """A data series for bar/line/area charts."""
    name: str
    values: Optional[list[list[Any]]] = None  # For bar: [[label, number], ...]
    points: Optional[list[list[Any]]] = None  # For line/area: [[x, y], ...]


class BarChartContent(BaseModel):
    """Content for BAR_CHART slides."""
    chart_title: str
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(min_length=1)


class PieSlice(BaseModel):
    """A single slice of a pie chart."""
    label: str
    value: float


class PieChartContent(BaseModel):
    """Content for PIE_CHART slides."""
    chart_title: str
    slices: list[PieSlice] = Field(min_length=1)


class LineChartContent(BaseModel):
    """Content for LINE_CHART slides."""
    chart_title: str
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(min_length=1)


class AreaChartContent(BaseModel):
    """Content for AREA_CHART slides."""
    chart_title: str
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(min_length=1)


class TableContent(BaseModel):
    """Content for TABLE slides."""
    table_title: str = ""
    headers: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)


class TimelineEvent(BaseModel):
    """A single event on a timeline."""
    year: str
    title: str
    description: str = ""


class TimelineContent(BaseModel):
    """Content for TIMELINE_INFOGRAPHIC slides."""
    events: list[TimelineEvent] = Field(min_length=1, max_length=7)


class ProcessStep(BaseModel):
    """A single step in a process flow."""
    number: int
    title: str
    description: str = ""


class ProcessFlowContent(BaseModel):
    """Content for PROCESS_FLOW_INFOGRAPHIC slides."""
    steps: list[ProcessStep] = Field(min_length=1, max_length=6)
    flow_direction: str = "horizontal"


class ComparisonDimension(BaseModel):
    """A single dimension in a comparison."""
    aspect: str
    left: str
    right: str


class ComparisonContent(BaseModel):
    """Content for COMPARISON_INFOGRAPHIC slides."""
    left_label: str
    right_label: str
    dimensions: list[ComparisonDimension] = Field(min_length=1)


class TakeawayItem(BaseModel):
    """A single takeaway."""
    icon_hint: str = "✓"
    text: str


class KeyTakeawaysContent(BaseModel):
    """Content for KEY_TAKEAWAYS slides."""
    takeaways: list[TakeawayItem] = Field(min_length=1, max_length=5)


class SectionDividerContent(BaseModel):
    """Content for SECTION_DIVIDER slides."""
    section_number: int = 1
    section_title: str
    section_subtitle: Optional[str] = None


# ──────────────────────────────────────────────
# Main slide plan item model
# ──────────────────────────────────────────────

# Map slide_type → expected content model
CONTENT_MODEL_MAP: dict[str, type[BaseModel]] = {
    "TITLE": TitleContent,
    "AGENDA": AgendaContent,
    "EXEC_SUMMARY": ExecSummaryContent,
    "CONTENT_BULLETS": ContentBulletsContent,
    "CONTENT_TWO_COLUMN": ContentTwoColumnContent,
    "STAT_HIGHLIGHT": StatHighlightContent,
    "BAR_CHART": BarChartContent,
    "PIE_CHART": PieChartContent,
    "LINE_CHART": LineChartContent,
    "AREA_CHART": AreaChartContent,
    "TABLE": TableContent,
    "TIMELINE_INFOGRAPHIC": TimelineContent,
    "PROCESS_FLOW_INFOGRAPHIC": ProcessFlowContent,
    "COMPARISON_INFOGRAPHIC": ComparisonContent,
    "KEY_TAKEAWAYS": KeyTakeawaysContent,
    "SECTION_DIVIDER": SectionDividerContent,
}


class SlidePlanItem(BaseModel):
    """A single slide in the presentation plan."""
    slide_number: int = Field(ge=1)
    slide_type: str
    title: str
    subtitle: Optional[str] = None
    content: dict[str, Any]
    speaker_notes: str = ""
    source_sections: list[str] = Field(default_factory=list)

    @field_validator("slide_type")
    @classmethod
    def validate_slide_type(cls, v: str) -> str:
        """Ensure slide_type is one of the known types."""
        v_upper = v.upper()
        if v_upper not in VALID_SLIDE_TYPES:
            raise ValueError(
                f"Invalid slide_type '{v}'. Must be one of: {VALID_SLIDE_TYPES}"
            )
        return v_upper

    def validate_content(self) -> list[str]:
        """Validate content dict against the type-specific schema.

        Returns:
            List of validation error messages (empty if valid).
        """
        model_cls = CONTENT_MODEL_MAP.get(self.slide_type)
        if model_cls is None:
            return [f"No content model defined for slide_type '{self.slide_type}'"]

        errors: list[str] = []
        try:
            model_cls.model_validate(self.content)
        except Exception as exc:
            errors.append(f"Slide {self.slide_number} ({self.slide_type}): {exc}")
        return errors


class SlidePlan(BaseModel):
    """Complete validated slide plan."""
    slides: list[SlidePlanItem] = Field(min_length=1)

    def validate_all(self) -> list[str]:
        """Run all validation checks on the plan.

        Enforces globally accepted deck structure (McKinsey/BCG style):
          Slide 1 = TITLE → Slide 2 = AGENDA → Slide 3 = EXEC_SUMMARY
          → content slides → Last = KEY_TAKEAWAYS

        Returns:
            List of all validation error strings.
        """
        errors: list[str] = []
        count = len(self.slides)
        types = [s.slide_type for s in self.slides]

        # ── Slide count ──
        if count < SLIDE_COUNT_MIN or count > SLIDE_COUNT_MAX:
            errors.append(
                f"Slide count {count} outside range [{SLIDE_COUNT_MIN}, {SLIDE_COUNT_MAX}]"
            )

        # ── Slide numbering (sequential 1..N) ──
        for i, slide in enumerate(self.slides):
            if slide.slide_number != i + 1:
                errors.append(
                    f"Slide numbering gap: expected {i + 1}, got {slide.slide_number}"
                )

        # ── Mandatory deck skeleton ──
        if count >= 1 and types[0] != "TITLE":
            errors.append("Slide 1 must be TITLE")
        if count >= 2 and types[1] != "AGENDA":
            errors.append("Slide 2 must be AGENDA")
        if count >= 3 and types[2] != "EXEC_SUMMARY":
            errors.append("Slide 3 must be EXEC_SUMMARY")
        if count >= 1 and types[-1] != "KEY_TAKEAWAYS":
            errors.append("Last slide must be KEY_TAKEAWAYS")

        # ── No consecutive SECTION_DIVIDER slides ──
        for i in range(len(types) - 1):
            if types[i] == "SECTION_DIVIDER" and types[i + 1] == "SECTION_DIVIDER":
                errors.append(
                    f"Consecutive SECTION_DIVIDER at slides {i + 1} and {i + 2}"
                )

        # ── At least one data visualization if source likely has numbers ──
        data_types = {"BAR_CHART", "PIE_CHART", "LINE_CHART", "AREA_CHART", "TABLE"}
        content_types = set(types)
        # Check if any source section mentions numeric signals (tables, percentages, etc.)
        has_source_data = any(
            "table" in str(s.source_sections).lower()
            or "data" in str(s.source_sections).lower()
            or "revenue" in str(s.source_sections).lower()
            or "metric" in str(s.source_sections).lower()
            for s in self.slides
        )
        if has_source_data and not content_types.intersection(data_types):
            errors.append(
                "Source has numeric/tabular data but no chart or table slide was created"
            )

        # ── Speaker notes should not be empty ──
        for slide in self.slides:
            if not slide.speaker_notes or not slide.speaker_notes.strip():
                errors.append(
                    f"Slide {slide.slide_number} ({slide.slide_type}) has empty speaker_notes"
                )

        # ── Validate individual slide content against type-specific schema ──
        for slide in self.slides:
            content_errors = slide.validate_content()
            errors.extend(content_errors)

        return errors
