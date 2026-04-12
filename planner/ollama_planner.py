"""
planner/ollama_planner.py — Local LLM planner using Ollama.

Single-stage architecture with JSON repair:
  - Qwen3:8b with think=False generates structured JSON slide plans directly.
  - The insight engine (Layer 2) already handles reasoning about data.
  - Truncated JSON is repaired by closing open brackets/braces.

Falls back to rule-based planner if Ollama is unreachable or JSON is invalid.
"""

from __future__ import annotations

import json
import logging
import re
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
from planner.slide_plan_schema import SlidePlan, SlidePlanItem

logger = logging.getLogger(__name__)

# ── Compact system prompt (minimized to save input tokens) ──
OLLAMA_SYSTEM = """Output ONLY a valid JSON array of slide objects. No explanation, no markdown fences.

Rules:
- Slide 1=TITLE, 2=AGENDA, 3=EXEC_SUMMARY, last=KEY_TAKEAWAYS
- {min_slides}-{max_slides} slides total
- Tables with numbers → BAR_CHART/PIE_CHART/LINE_CHART (NOT bullets)
- Chart values must be numbers, not strings
- Max 6 bullets, each ≤7 words
- Every slide needs speaker_notes (2-3 sentences)
- Keep speaker_notes SHORT. Keep bullet text SHORT.
- VARIETY IS CRITICAL: use at least 4 different slide types beyond the fixed ones (TITLE/AGENDA/EXEC_SUMMARY/KEY_TAKEAWAYS)

Type selection guide:
- 2-3 key numbers/stats/KPIs → STAT_HIGHLIGHT
- Market share, distribution, composition → PIE_CHART
- Trends over time → LINE_CHART or AREA_CHART
- Comparisons across categories → BAR_CHART
- Raw tabular data (many columns) → TABLE
- Sequential steps/process → PROCESS_FLOW_INFOGRAPHIC
- Chronological events/milestones → TIMELINE_INFOGRAPHIC
- Two things compared (pros/cons, before/after) → COMPARISON_INFOGRAPHIC
- Two parallel topics → CONTENT_TWO_COLUMN
- Transition between major topics → SECTION_DIVIDER
- General points → CONTENT_BULLETS (use sparingly, prefer visual types)

All types: TITLE, AGENDA, EXEC_SUMMARY, CONTENT_BULLETS, CONTENT_TWO_COLUMN,
STAT_HIGHLIGHT, BAR_CHART, PIE_CHART, LINE_CHART, AREA_CHART, TABLE,
TIMELINE_INFOGRAPHIC, PROCESS_FLOW_INFOGRAPHIC, COMPARISON_INFOGRAPHIC,
KEY_TAKEAWAYS, SECTION_DIVIDER"""

# ── Compact user prompt with inline schemas ──
OLLAMA_USER = """Generate a JSON slide plan for this document.

Title: {title}
Sections: {section_summary}

{insights_block}

Target: {target_count} slides

Schemas (follow exactly):
TITLE: {{"slide_number":1,"slide_type":"TITLE","title":"...","subtitle":null,"content":{{"headline":"...","subheadline":"...","presenter":null}},"speaker_notes":"...","source_sections":[]}}
AGENDA: {{"slide_number":2,"slide_type":"AGENDA","title":"Agenda","subtitle":null,"content":{{"items":[{{"number":1,"topic":"..."}}]}},"speaker_notes":"...","source_sections":[]}}
EXEC_SUMMARY: {{"slide_number":3,"slide_type":"EXEC_SUMMARY","title":"Executive Summary","subtitle":null,"content":{{"insights":["..."],"key_metric":"..."}},"speaker_notes":"...","source_sections":["..."]}}
CONTENT_BULLETS: {{"slide_number":N,"slide_type":"CONTENT_BULLETS","title":"...","subtitle":null,"content":{{"bullets":[{{"text":"...","sub_bullets":null}}]}},"speaker_notes":"...","source_sections":["..."]}}
CONTENT_TWO_COLUMN: {{"slide_number":N,"slide_type":"CONTENT_TWO_COLUMN","title":"...","subtitle":null,"content":{{"left":{{"heading":"...","points":["..."]}},"right":{{"heading":"...","points":["..."]}}}},"speaker_notes":"...","source_sections":["..."]}}
STAT_HIGHLIGHT: {{"slide_number":N,"slide_type":"STAT_HIGHLIGHT","title":"...","subtitle":null,"content":{{"stats":[{{"value":"$2.5M","label":"Revenue","context":"Up 25% YoY"}}]}},"speaker_notes":"...","source_sections":["..."]}}
BAR_CHART: {{"slide_number":N,"slide_type":"BAR_CHART","title":"...","subtitle":null,"content":{{"chart_title":"...","x_label":"...","y_label":"...","series":[{{"name":"...","values":[["Label",123]]}}]}},"speaker_notes":"...","source_sections":["..."]}}
PIE_CHART: {{"slide_number":N,"slide_type":"PIE_CHART","title":"...","subtitle":null,"content":{{"chart_title":"...","slices":[{{"label":"...","value":45}}]}},"speaker_notes":"...","source_sections":["..."]}}
LINE_CHART: {{"slide_number":N,"slide_type":"LINE_CHART","title":"...","subtitle":null,"content":{{"chart_title":"...","x_label":"...","y_label":"...","series":[{{"name":"...","points":[["2020",100]]}}]}},"speaker_notes":"...","source_sections":["..."]}}
AREA_CHART: {{"slide_number":N,"slide_type":"AREA_CHART","title":"...","subtitle":null,"content":{{"chart_title":"...","x_label":"...","y_label":"...","series":[{{"name":"...","points":[["2020",100]]}}]}},"speaker_notes":"...","source_sections":["..."]}}
TABLE: {{"slide_number":N,"slide_type":"TABLE","title":"...","subtitle":null,"content":{{"table_title":"...","headers":["Col1","Col2","Col3"],"rows":[["a","b","c"]]}},"speaker_notes":"...","source_sections":["..."]}}
TIMELINE_INFOGRAPHIC: {{"slide_number":N,"slide_type":"TIMELINE_INFOGRAPHIC","title":"...","subtitle":null,"content":{{"events":[{{"year":"2020","title":"...","description":"..."}}]}},"speaker_notes":"...","source_sections":["..."]}}
PROCESS_FLOW_INFOGRAPHIC: {{"slide_number":N,"slide_type":"PROCESS_FLOW_INFOGRAPHIC","title":"...","subtitle":null,"content":{{"steps":[{{"number":1,"title":"...","description":"..."}}],"flow_direction":"horizontal"}},"speaker_notes":"...","source_sections":["..."]}}
COMPARISON_INFOGRAPHIC: {{"slide_number":N,"slide_type":"COMPARISON_INFOGRAPHIC","title":"...","subtitle":null,"content":{{"left_label":"Option A","right_label":"Option B","dimensions":[{{"aspect":"Cost","left":"$100","right":"$200"}}]}},"speaker_notes":"...","source_sections":["..."]}}
SECTION_DIVIDER: {{"slide_number":N,"slide_type":"SECTION_DIVIDER","title":"...","subtitle":null,"content":{{"section_number":1,"section_title":"...","section_subtitle":"..."}},"speaker_notes":"...","source_sections":[]}}
KEY_TAKEAWAYS: {{"slide_number":N,"slide_type":"KEY_TAKEAWAYS","title":"Key Takeaways","subtitle":null,"content":{{"takeaways":[{{"icon_hint":"📈","text":"..."}}]}},"speaker_notes":"...","source_sections":[]}}

IMPORTANT: Prefer STAT_HIGHLIGHT, TABLE, PIE_CHART, COMPARISON_INFOGRAPHIC, PROCESS_FLOW_INFOGRAPHIC, TIMELINE_INFOGRAPHIC over plain CONTENT_BULLETS when data supports it.

Output the JSON array now. Start with [ and end with ]."""


def _ollama_chat(
    model: str,
    system: str,
    user: str,
    temperature: float = OLLAMA_TEMPERATURE,
    max_tokens: int = OLLAMA_MAX_TOKENS,
) -> tuple[str | None, dict]:
    """Call Ollama chat API with thinking disabled.

    Returns:
        Tuple of (response text or None, metadata dict with token counts).
    """
    url = "{}/api/chat".format(OLLAMA_BASE_URL)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": 16384,
        },
    }

    meta = {"eval_count": 0, "total_sec": 0, "done_reason": ""}
    try:
        logger.info("Calling Ollama model=%s (timeout=%ds, num_predict=%d)",
                     model, OLLAMA_TIMEOUT_SEC, max_tokens)
        resp = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        content = message.get("content", "").strip()
        meta["eval_count"] = data.get("eval_count", 0)
        meta["total_sec"] = data.get("total_duration", 0) / 1e9
        meta["done_reason"] = data.get("done_reason", "")

        # Also check thinking field (qwen3 may put content there)
        thinking = message.get("thinking", "")
        if thinking and not content:
            logger.warning("Response in 'thinking' field (not 'content'), using it")
            content = thinking.strip()

        if content:
            logger.info(
                "Ollama: %d chars, %d tokens, %.1fs, done_reason=%s, model=%s",
                len(content), meta["eval_count"], meta["total_sec"],
                meta["done_reason"], model,
            )
            # Dump raw response for debugging
            try:
                with open("/tmp/ollama_last_response.txt", "w") as _f:
                    _f.write(content)
                logger.debug("Raw response dumped to /tmp/ollama_last_response.txt")
            except Exception:
                pass
        return content or None, meta
    except requests.ConnectionError:
        logger.error("Cannot connect to Ollama at %s", OLLAMA_BASE_URL)
        return None, meta
    except requests.Timeout:
        logger.error("Ollama request timed out after %ds", OLLAMA_TIMEOUT_SEC)
        return None, meta
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)
        return None, meta


def _check_ollama_available() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        resp = requests.get("{}/api/tags".format(OLLAMA_BASE_URL), timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _build_section_summary(ast_dict: dict[str, Any]) -> str:
    """Build ultra-compact section summary to minimize input tokens."""
    sections = ast_dict.get("sections", [])
    lines = []
    for sec in sections:
        heading = sec.get("heading", "?")
        blocks = sec.get("blocks", [])
        parts = [heading]
        for b in blocks:
            if b["type"] == "table":
                headers = b.get("content", {}).get("headers", [])
                rows = b.get("content", {}).get("rows", [])
                row_preview = ""
                if rows:
                    row_preview = " e.g. " + str(rows[0])
                parts.append("[TABLE: {} cols, {} rows{}]".format(
                    "|".join(headers), len(rows), row_preview))
            elif b["type"] in ("bullet_list", "ordered_list"):
                items = b.get("content", [])
                parts.append("[LIST: {} items]".format(len(items)))
        body = sec.get("body", "")
        if body and not any("[TABLE" in p or "[LIST" in p for p in parts[1:]):
            parts.append("({} words)".format(len(body.split())))
        lines.append(" — ".join(parts))
    return "\n".join(lines)


def _build_insights_block(insights: Any) -> str:
    """Build compact insights block for prompts."""
    if not insights or not insights.executive_insights:
        return ""

    parts = ["DATA INSIGHTS (use these in EXEC_SUMMARY and KEY_TAKEAWAYS):"]
    for i, e in enumerate(insights.executive_insights[:4], 1):
        parts.append("{}. {}".format(i, e))

    if insights.key_metric:
        parts.append("Key metric: {}".format(insights.key_metric))

    if insights.takeaways:
        parts.append("Takeaways: " + "; ".join(t.text for t in insights.takeaways[:5]))

    return "\n".join(parts)


def plan_slides_ollama(
    ast_dict: dict[str, Any],
    target_count: int = SLIDE_COUNT_DEFAULT,
    retry_hints: list[str] | None = None,
    insights: Any = None,
) -> list[dict[str, Any]]:
    """Generate slide plan using local Ollama model (single-stage).

    Uses Qwen3:8b with thinking disabled for direct JSON generation.
    The insight engine already handles reasoning about data, so no
    separate reasoning stage is needed.

    Falls back to rule-based planner if Ollama is unavailable or
    JSON generation fails after retries.
    """
    if not _check_ollama_available():
        logger.warning("Ollama not available — falling back to rule-based planner")
        from planner.fallback_planner import plan_slides_fallback
        return plan_slides_fallback(ast_dict, target_count, insights=insights)

    target_count = max(SLIDE_COUNT_MIN, min(SLIDE_COUNT_MAX, target_count))

    model = OLLAMA_REASONING_MODEL
    insights_block = _build_insights_block(insights)

    system_msg = OLLAMA_SYSTEM.format(
        min_slides=SLIDE_COUNT_MIN,
        max_slides=SLIDE_COUNT_MAX,
    )

    user_msg = OLLAMA_USER.format(
        title=ast_dict.get("title", "Presentation"),
        section_summary=_build_section_summary(ast_dict),
        target_count=target_count,
        insights_block=insights_block,
    )

    if retry_hints:
        user_msg += "\n\nFix these issues: " + "; ".join(retry_hints[:3])

    last_errors = []

    for attempt in range(OLLAMA_RETRY_COUNT):
        logger.info("Generation attempt %d/%d with %s", attempt + 1, OLLAMA_RETRY_COUNT, model)

        current_msg = user_msg
        if attempt > 0 and last_errors:
            current_msg = user_msg + "\n\nPrevious errors: " + "; ".join(last_errors[:2]) + "\nFix and return valid JSON."

        response, meta = _ollama_chat(
            model=model,
            system=system_msg,
            user=current_msg,
            temperature=0.3 if attempt == 0 else 0.5,
            max_tokens=OLLAMA_MAX_TOKENS,
        )

        if not response:
            last_errors = ["Empty response from Ollama"]
            continue

        # Parse JSON — with truncation repair
        slides_data = _extract_json(response)

        # If JSON extraction failed, always try repair (not just on truncation)
        if slides_data is None:
            logger.warning("JSON extraction failed (done_reason=%s), attempting repair", meta.get("done_reason"))
            slides_data = _repair_truncated_json(response)

        if slides_data is None:
            last_errors = ["JSON parse failed: {}".format(response[:150])]
            logger.warning("JSON parse failed on attempt %d: %s", attempt + 1, response[:150])
            # Dump first and last 300 chars for debugging
            logger.debug("Response HEAD: %s", repr(response[:300]))
            logger.debug("Response TAIL: %s", repr(response[-300:]))
            continue

        # Validate with Pydantic (lenient — skip if ≥ 5 valid slides)
        validation_errors = _validate_slide_plan(slides_data)
        if validation_errors:
            # If we have enough valid slides, use them despite warnings
            if len(slides_data) >= 5:
                logger.warning(
                    "Validation warnings (proceeding with %d slides): %s",
                    len(slides_data), "; ".join(validation_errors[:2]),
                )
                return slides_data
            last_errors = validation_errors
            logger.warning("Validation failed on attempt %d: %s",
                           attempt + 1, "; ".join(validation_errors[:3]))
            continue

        logger.info("Ollama planner succeeded on attempt %d with %d slides",
                     attempt + 1, len(slides_data))
        return slides_data

    # All attempts failed
    logger.warning(
        "Ollama planner failed after %d attempts — using fallback. Errors: %s",
        OLLAMA_RETRY_COUNT, "; ".join(last_errors[:3]),
    )
    from planner.fallback_planner import plan_slides_fallback
    return plan_slides_fallback(ast_dict, target_count, insights=insights)


def _extract_json(text: str) -> list[dict[str, Any]] | None:
    """Extract a JSON array from LLM response text."""
    cleaned = text.strip()

    # Remove ALL think tags — handle both closed and unclosed
    # Pattern 1: <think>...</think> (closed)
    if "<think>" in cleaned:
        think_end = cleaned.rfind("</think>")
        if think_end != -1:
            # Remove everything from <think> to </think>
            cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()
        else:
            # Unclosed <think> — remove everything from <think> to end, or to first [
            think_start = cleaned.find("<think>")
            bracket_pos = cleaned.find("[", think_start)
            if bracket_pos != -1:
                cleaned = cleaned[bracket_pos:]
            else:
                cleaned = cleaned[:think_start].strip()

    # Remove /think or /no_think tags (Qwen3 artifacts)
    cleaned = re.sub(r'</?(no_)?think>', '', cleaned).strip()

    # Strip markdown code fences
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "slides" in data:
            return data["slides"]
    except json.JSONDecodeError as e:
        logger.debug("Direct parse failed at pos %d: %s", e.pos, e.msg)

    # Find JSON array boundaries
    bracket_start = cleaned.find("[")
    bracket_end = cleaned.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        json_slice = cleaned[bracket_start:bracket_end + 1]
        try:
            data = json.loads(json_slice)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError as e:
            logger.debug("Bracket extract failed at pos %d: %s", e.pos, e.msg)
            # Try fixing common issues: trailing commas, unescaped newlines
            fixed = _fix_common_json_issues(json_slice)
            if fixed:
                try:
                    data = json.loads(fixed)
                    if isinstance(data, list):
                        logger.info("JSON fixed by common-issue repair")
                        return data
                except json.JSONDecodeError:
                    pass

    return None


def _fix_common_json_issues(text: str) -> str | None:
    """Fix common JSON issues from LLM output."""
    fixed = text
    # Remove trailing commas before ] or }
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    # Remove any embedded <think> blocks within JSON
    fixed = re.sub(r'<think>.*?</think>', '', fixed, flags=re.DOTALL)
    fixed = re.sub(r'<think>[^<]*$', '', fixed)  # unclosed at end
    # Fix unescaped newlines inside strings (replace with space)
    # This is tricky — only do it if the basic fix helps
    return fixed


def _repair_truncated_json(text: str) -> list[dict[str, Any]] | None:
    """Attempt to repair truncated JSON by closing open structures.

    When the model hits its token limit, the JSON array gets cut off mid-object.
    This function tries to salvage the complete slide objects before the truncation.
    """
    cleaned = text.strip()

    # Find the JSON array start
    start = cleaned.find("[")
    if start == -1:
        return None

    json_text = cleaned[start:]

    # Strategy 1: Find the last complete object (ends with }) followed by , or ]
    # Look for },\n  { or }\n] patterns to find complete objects
    last_complete = -1
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(json_text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == '{':
            depth_brace += 1
        elif ch == '}':
            depth_brace -= 1
            if depth_brace == 0 and depth_bracket == 1:
                # Found end of a top-level object in the array
                last_complete = i
        elif ch == '[':
            depth_bracket += 1
        elif ch == ']':
            depth_bracket -= 1

    if last_complete > 0:
        # Truncate to the last complete object, close the array
        truncated = json_text[:last_complete + 1] + "]"
        try:
            data = json.loads(truncated)
            if isinstance(data, list) and len(data) >= 3:
                logger.info("JSON repair succeeded: recovered %d complete slides", len(data))
                return data
        except json.JSONDecodeError:
            pass

    # Strategy 2: progressively strip from the end and try to close
    for trim in range(1, min(len(json_text), 2000)):
        candidate = json_text[:len(json_text) - trim]
        # Find last }, close array
        last_brace = candidate.rfind("}")
        if last_brace > 0:
            attempt = candidate[:last_brace + 1] + "]"
            try:
                data = json.loads(attempt)
                if isinstance(data, list) and len(data) >= 3:
                    logger.info("JSON repair (strategy 2): recovered %d slides", len(data))
                    return data
            except json.JSONDecodeError:
                continue

    return None


def _validate_slide_plan(slides_data: list[dict[str, Any]]) -> list[str]:
    """Validate slide plan against Pydantic schemas."""
    errors = []
    try:
        slide_items = [SlidePlanItem.model_validate(s) for s in slides_data]
        plan = SlidePlan(slides=slide_items)
        errors = plan.validate_all()
    except Exception as exc:
        errors.append("Schema validation error: {}".format(exc))
    return errors


def warmup_model() -> bool:
    """Pre-warm the Ollama model by sending a tiny request.

    Call this at app startup to load model weights into GPU VRAM
    so the first real request doesn't pay the cold-start penalty.
    """
    if not _check_ollama_available():
        return False

    model = OLLAMA_REASONING_MODEL
    logger.info("Pre-warming model %s...", model)
    url = "{}/api/chat".format(OLLAMA_BASE_URL)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "stream": False,
        "think": False,
        "options": {"num_predict": 5},
    }
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code == 200:
            logger.info("Model %s pre-warmed successfully", model)
            return True
    except Exception as exc:
        logger.warning("Model warmup failed: %s", exc)
    return False
