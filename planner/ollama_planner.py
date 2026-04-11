"""
planner/ollama_planner.py — Local LLM planner using Ollama (Qwen3 + Qwen3.5).

Two-model architecture:
  1. Qwen3:8b (thinking mode) — reasons about document structure, identifies
     key themes, charts, and narrative flow.
  2. Qwen3.5:9b — generates the structured JSON slide plan from the
     reasoning output.

Falls back to rule-based planner if Ollama is unreachable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_REASONING_MODEL,
    OLLAMA_GENERATION_MODEL,
    OLLAMA_TIMEOUT_SEC,
    OLLAMA_MAX_TOKENS,
    OLLAMA_TEMPERATURE,
    OLLAMA_RETRY_COUNT,
    SLIDE_COUNT_MIN,
    SLIDE_COUNT_MAX,
    SLIDE_COUNT_DEFAULT,
)
from planner.prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    INSIGHTS_ADDENDUM,
    RETRY_PROMPT,
)
from planner.slide_plan_schema import SlidePlan, SlidePlanItem

logger = logging.getLogger(__name__)

# ── Reasoning prompt (for Qwen3 thinking mode) ──
REASONING_PROMPT = """Analyze this document AST and decide the best slide plan strategy.

Document:
{ast_summary}

Target: {target_count} slides (range {min_slides}–{max_slides})

For each section, decide:
1. Best slide_type (CONTENT_BULLETS, BAR_CHART, PIE_CHART, LINE_CHART, TABLE, STAT_HIGHLIGHT, TIMELINE_INFOGRAPHIC, PROCESS_FLOW_INFOGRAPHIC, COMPARISON_INFOGRAPHIC, SECTION_DIVIDER)
2. Whether tables should become charts (and which chart type)
3. Key narrative flow and story arc

{insights_block}

Output a concise plan as a numbered list:
- Slide 1: TITLE — "{{title}}"
- Slide 2: AGENDA — topics list
- Slide 3: EXEC_SUMMARY — top insights
- Slide 4+: one line per content slide with type and source section
- Last: KEY_TAKEAWAYS

Be specific about chart types for data tables. Think step by step."""

# ── Generation prompt (simplified for local LLM) ──
GENERATION_SYSTEM = """You are a JSON generator that creates slide plans for presentations.
You output ONLY valid JSON arrays. No markdown fences, no commentary, no explanation.

HARD RULES:
1. Return a JSON array of slide objects. Nothing else.
2. Slide count: {min_slides}–{max_slides}.
3. Slide 1=TITLE, Slide 2=AGENDA, Slide 3=EXEC_SUMMARY, Last=KEY_TAKEAWAYS.
4. Numeric tables → chart slides (BAR_CHART/PIE_CHART/LINE_CHART), NOT bullets.
5. Chart values must be numbers, not strings.
6. Max 6 bullets per slide, each ≤7 words.
7. Every slide needs speaker_notes (2-3 sentences).

SLIDE TYPES: TITLE, AGENDA, EXEC_SUMMARY, CONTENT_BULLETS, CONTENT_TWO_COLUMN,
STAT_HIGHLIGHT, BAR_CHART, PIE_CHART, LINE_CHART, AREA_CHART, TABLE,
TIMELINE_INFOGRAPHIC, PROCESS_FLOW_INFOGRAPHIC, COMPARISON_INFOGRAPHIC,
KEY_TAKEAWAYS, SECTION_DIVIDER"""

GENERATION_USER = """Create a slide plan from this document analysis.

Reasoning plan to follow:
{reasoning_plan}

Document AST:
{ast_json}

Target: {target_count} slides

{insights_block}

Each slide object schema:
{{
  "slide_number": int,
  "slide_type": str,
  "title": str,
  "subtitle": str | null,
  "content": {{...}},
  "speaker_notes": str,
  "source_sections": [str]
}}

Content schemas:
- TITLE: {{"headline": str, "subheadline": str, "presenter": null}}
- AGENDA: {{"items": [{{"number": int, "topic": str}}]}}
- EXEC_SUMMARY: {{"insights": [str], "key_metric": str|null}}
- CONTENT_BULLETS: {{"bullets": [{{"text": str, "sub_bullets": [str]|null}}]}}
- STAT_HIGHLIGHT: {{"stats": [{{"value": str, "label": str, "context": str}}]}}
- BAR_CHART: {{"chart_title": str, "x_label": str, "y_label": str, "series": [{{"name": str, "values": [[str, number]]}}]}}
- PIE_CHART: {{"chart_title": str, "slices": [{{"label": str, "value": number}}]}}
- LINE_CHART: {{"chart_title": str, "x_label": str, "y_label": str, "series": [{{"name": str, "points": [[x, y]]}}]}}
- TABLE: {{"table_title": str, "headers": [str], "rows": [[str]]}}
- KEY_TAKEAWAYS: {{"takeaways": [{{"icon_hint": str, "text": str}}]}}
- SECTION_DIVIDER: {{"section_number": int, "section_title": str, "section_subtitle": str|null}}

Return ONLY the JSON array. Start with '[' and end with ']'."""


def _ollama_chat(
    model: str,
    system: str,
    user: str,
    temperature: float = OLLAMA_TEMPERATURE,
    max_tokens: int = OLLAMA_MAX_TOKENS,
    think: bool | None = None,
) -> str | None:
    """Call Ollama chat API.

    Args:
        model: Model name (e.g., "qwen3:8b").
        system: System prompt.
        user: User prompt.
        temperature: Sampling temperature.
        max_tokens: Max tokens in response.
        think: Enable/disable thinking mode. None = model default.
              False = disable thinking (for structured JSON output).
              True = enable thinking (for reasoning).

    Returns:
        Response text, or None on failure.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    # Control thinking mode for Qwen3/Qwen3.5 models
    if think is not None:
        payload["think"] = think

    try:
        logger.info("Calling Ollama model=%s (timeout=%ds, think=%s)", model, OLLAMA_TIMEOUT_SEC, think)
        resp = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        content = message.get("content", "")
        thinking = message.get("thinking", "")

        # For thinking models: content has the answer, thinking has the reasoning
        # When think=True, content may be empty and reasoning is in thinking field
        result = content.strip()
        if not result and thinking:
            result = thinking.strip()

        if result:
            eval_count = data.get("eval_count", 0)
            total_sec = data.get("total_duration", 0) / 1e9
            logger.info(
                "Ollama response: %d chars, %d tokens, %.1fs total, model=%s",
                len(result), eval_count, total_sec, model,
            )
        return result or None
    except requests.ConnectionError:
        logger.error("Cannot connect to Ollama at %s", OLLAMA_BASE_URL)
        return None
    except requests.Timeout:
        logger.error("Ollama request timed out after %ds", OLLAMA_TIMEOUT_SEC)
        return None
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)
        return None


def _check_ollama_available() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _build_ast_summary(ast_dict: dict[str, Any]) -> str:
    """Build a compact summary of the AST for the reasoning model.

    Keeps it short to fit in context window of smaller models.
    """
    title = ast_dict.get("title", "Untitled")
    sections = ast_dict.get("sections", [])
    metadata = ast_dict.get("metadata", {})

    lines = [
        f"Title: {title}",
        f"Word count: {metadata.get('word_count', 0)}",
        f"Sections: {len(sections)}",
        f"Has numeric data: {metadata.get('has_numeric_data', False)}",
        "",
    ]

    for sec in sections:
        heading = sec.get("heading", "?")
        blocks = sec.get("blocks", [])
        body_preview = sec.get("body", "")[:150]

        block_types = [b["type"] for b in blocks]
        table_count = sum(1 for b in blocks if b["type"] == "table")
        list_count = sum(1 for b in blocks if b["type"] in ("bullet_list", "ordered_list"))

        line = f"## {heading}"
        if table_count:
            # Summarize table headers
            for b in blocks:
                if b["type"] == "table":
                    headers = b.get("content", {}).get("headers", [])
                    rows = b.get("content", {}).get("rows", [])
                    line += f" [TABLE: {headers}, {len(rows)} rows]"
        if list_count:
            line += f" [LISTS: {list_count}]"
        if body_preview:
            line += f"\n  Preview: {body_preview}..."

        lines.append(line)

    return "\n".join(lines)


def _build_insights_block(insights: Any) -> str:
    """Build insights block for prompts."""
    if not insights or not insights.executive_insights:
        return ""

    parts = ["PRE-COMPUTED DATA INSIGHTS:"]
    parts.append("Executive insights: " + "; ".join(insights.executive_insights[:4]))

    if insights.key_metric:
        parts.append(f"Key metric: {insights.key_metric}")

    for si in insights.sections:
        if si.speaker_note_fragment:
            parts.append(f"  {si.heading}: {si.speaker_note_fragment}")

    if insights.takeaways:
        parts.append("Takeaways: " + "; ".join(t.text for t in insights.takeaways[:5]))

    return "\n".join(parts)


def plan_slides_ollama(
    ast_dict: dict[str, Any],
    target_count: int = SLIDE_COUNT_DEFAULT,
    retry_hints: list[str] | None = None,
    insights: Any = None,
) -> list[dict[str, Any]]:
    """Generate slide plan using local Ollama models (two-stage).

    Stage 1: Reasoning model with thinking enabled — reasons about
             optimal slide structure and chart types.
    Stage 2: Same model with thinking disabled — generates structured
             JSON slide plan (avoids GPU model-swap overhead).

    Falls back to rule-based planner if Ollama is unavailable.

    Args:
        ast_dict: Structured AST dict from the parser.
        target_count: Desired slide count.
        retry_hints: Optional hints from previous validation failure.
        insights: Optional DocumentInsights from insight engine.

    Returns:
        List of validated slide plan dicts.
    """
    if not _check_ollama_available():
        logger.warning("Ollama not available — falling back to rule-based planner")
        from planner.fallback_planner import plan_slides_fallback
        return plan_slides_fallback(ast_dict, target_count, insights=insights)

    target_count = max(SLIDE_COUNT_MIN, min(SLIDE_COUNT_MAX, target_count))
    insights_block = _build_insights_block(insights)

    # Use reasoning model for both stages (avoids GPU model swap overhead)
    model = OLLAMA_REASONING_MODEL

    # ── Stage 1: Reasoning with thinking enabled ──
    logger.info("Stage 1: Reasoning with %s (think=True)", model)
    ast_summary = _build_ast_summary(ast_dict)

    reasoning_prompt = REASONING_PROMPT.format(
        ast_summary=ast_summary,
        target_count=target_count,
        min_slides=SLIDE_COUNT_MIN,
        max_slides=SLIDE_COUNT_MAX,
        insights_block=insights_block,
    )

    reasoning_plan = _ollama_chat(
        model=model,
        system="You are an expert presentation strategist. Think step by step about the best slide structure.",
        user=reasoning_prompt,
        temperature=0.6,
        max_tokens=2048,
        think=True,
    )

    if not reasoning_plan:
        logger.warning("Reasoning stage failed — using direct generation")
        reasoning_plan = f"Create {target_count} slides following standard structure: TITLE, AGENDA, EXEC_SUMMARY, content slides, KEY_TAKEAWAYS."

    logger.info("Reasoning plan: %d chars", len(reasoning_plan))

    # ── Stage 2: JSON generation with thinking DISABLED ──
    ast_json_str = json.dumps(ast_dict, indent=2, default=str)
    # Truncate large ASTs to fit in context
    if len(ast_json_str) > 60_000:
        logger.warning("AST JSON too large (%d chars), truncating for local model", len(ast_json_str))
        ast_json_str = ast_json_str[:60_000] + "\n... [TRUNCATED]"

    system_msg = GENERATION_SYSTEM.format(
        min_slides=SLIDE_COUNT_MIN,
        max_slides=SLIDE_COUNT_MAX,
    )

    user_msg = GENERATION_USER.format(
        reasoning_plan=reasoning_plan,
        ast_json=ast_json_str,
        target_count=target_count,
        insights_block=insights_block,
    )

    if retry_hints:
        user_msg += "\n\nFix these issues from previous attempt:\n"
        for hint in retry_hints:
            user_msg += f"- {hint}\n"

    # Try generation with retries
    last_errors: list[str] = []

    for attempt in range(OLLAMA_RETRY_COUNT):
        logger.info(
            "Stage 2: Generation attempt %d/%d with %s (think=False)",
            attempt + 1, OLLAMA_RETRY_COUNT, model,
        )

        if attempt > 0 and last_errors:
            # Add error context to the prompt
            user_msg_retry = user_msg + f"\n\nPrevious errors: {'; '.join(last_errors[:3])}\nFix and return valid JSON array."
        else:
            user_msg_retry = user_msg

        response = _ollama_chat(
            model=model,
            system=system_msg,
            user=user_msg_retry,
            temperature=OLLAMA_TEMPERATURE,
            max_tokens=OLLAMA_MAX_TOKENS,
            think=False,  # Disable thinking for structured JSON output
        )

        if not response:
            last_errors = ["Empty response from Ollama"]
            continue

        # Parse JSON from response
        slides_data = _extract_json(response)
        if slides_data is None:
            last_errors = [f"Failed to parse JSON: {response[:200]}"]
            logger.warning("JSON parse failed on attempt %d", attempt + 1)
            continue

        # Validate with Pydantic
        validation_errors = _validate_slide_plan(slides_data)
        if validation_errors:
            last_errors = validation_errors
            logger.warning(
                "Validation failed on attempt %d: %s",
                attempt + 1, "; ".join(validation_errors[:3]),
            )
            continue

        logger.info(
            "Ollama planner succeeded on attempt %d with %d slides",
            attempt + 1, len(slides_data),
        )
        return slides_data

    # All attempts failed — fall back to rule-based
    logger.warning(
        "Ollama planner failed after %d attempts — using fallback. Last errors: %s",
        OLLAMA_RETRY_COUNT, "; ".join(last_errors[:3]),
    )
    from planner.fallback_planner import plan_slides_fallback
    return plan_slides_fallback(ast_dict, target_count, insights=insights)


def _extract_json(text: str) -> list[dict[str, Any]] | None:
    """Extract a JSON array from LLM response text."""
    cleaned = text.strip()

    # Remove thinking tags if present (Qwen3 thinking mode)
    if "<think>" in cleaned:
        think_end = cleaned.rfind("</think>")
        if think_end != -1:
            cleaned = cleaned[think_end + len("</think>"):].strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "slides" in data:
            return data["slides"]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in text
    bracket_start = cleaned.find("[")
    bracket_end = cleaned.rfind("]")
    if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
        try:
            data = json.loads(cleaned[bracket_start:bracket_end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _validate_slide_plan(slides_data: list[dict[str, Any]]) -> list[str]:
    """Validate slide plan against Pydantic schemas."""
    errors: list[str] = []
    try:
        slide_items = [SlidePlanItem.model_validate(s) for s in slides_data]
        plan = SlidePlan(slides=slide_items)
        errors = plan.validate_all()
    except Exception as exc:
        errors.append(f"Schema validation error: {exc}")
    return errors
