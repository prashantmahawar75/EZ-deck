"""
planner/ai_planner.py — Layer 2: Calls Claude API to generate slide plan JSON.

Implements exponential backoff, Pydantic validation with self-healing retries,
and falls back to the rule-based planner when the API is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from config import (
    AI_PRIMARY_MODEL,
    AI_FALLBACK_MODEL,
    AI_MAX_TOKENS,
    AI_TEMPERATURE,
    API_RETRY_COUNT,
    API_RETRY_DELAYS_SEC,
    SLIDE_COUNT_MIN,
    SLIDE_COUNT_MAX,
    SLIDE_COUNT_DEFAULT,
    MAX_SECTIONS_BEFORE_CLUSTERING,
    PlannerError,
)
from planner.prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    RETRY_PROMPT,
    COUNT_ADJUSTMENT_PROMPT,
    CLUSTERING_PROMPT,
)
from planner.slide_plan_schema import SlidePlan, SlidePlanItem

logger = logging.getLogger(__name__)


def plan_slides(
    ast_dict: dict[str, Any],
    target_count: int = SLIDE_COUNT_DEFAULT,
    retry_hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate a slide plan from the parsed AST using Claude API.

    Args:
        ast_dict: Structured AST dict from the parser.
        target_count: Desired slide count (clamped to valid range).
        retry_hints: Optional hints from a previous validation failure.

    Returns:
        List of validated slide plan dicts.

    Raises:
        PlannerError: If all attempts (AI + fallback) fail.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — falling back to rule-based planner"
        )
        from planner.fallback_planner import plan_slides_fallback
        return plan_slides_fallback(ast_dict, target_count)

    target_count = max(SLIDE_COUNT_MIN, min(SLIDE_COUNT_MAX, target_count))

    # Pre-process: cluster sections if there are too many
    working_ast = _maybe_cluster_sections(ast_dict, api_key, target_count)

    # Build the prompt
    ast_json_str = json.dumps(working_ast, indent=2, default=str)

    # Truncate if the AST is very large (keep under ~100K chars for the API)
    if len(ast_json_str) > 100_000:
        logger.warning("AST JSON too large (%d chars), truncating", len(ast_json_str))
        ast_json_str = ast_json_str[:100_000] + "\n... [TRUNCATED]"

    system_msg = SYSTEM_PROMPT.format(
        min_slides=SLIDE_COUNT_MIN,
        max_slides=SLIDE_COUNT_MAX,
    )

    user_msg = USER_PROMPT.format(
        ast_json=ast_json_str,
        target_count=target_count,
        min_slides=SLIDE_COUNT_MIN,
        max_slides=SLIDE_COUNT_MAX,
    )

    if retry_hints:
        user_msg += "\n\nAdditional guidance from previous validation:\n"
        for hint in retry_hints:
            user_msg += f"- {hint}\n"

    # Call the AI with retries
    raw_json = _call_claude_with_retries(api_key, system_msg, user_msg, ast_json_str)

    if raw_json is None:
        logger.warning("AI planner failed after all retries — using fallback")
        from planner.fallback_planner import plan_slides_fallback
        return plan_slides_fallback(ast_dict, target_count)

    return raw_json


def _call_claude_with_retries(
    api_key: str,
    system_msg: str,
    user_msg: str,
    ast_json_str: str,
) -> list[dict[str, Any]] | None:
    """Call Claude API with exponential backoff and validation retries.

    Args:
        api_key: Anthropic API key.
        system_msg: System prompt.
        user_msg: User prompt.
        ast_json_str: AST as JSON string (for retry prompts).

    Returns:
        Validated list of slide plan dicts, or None if all retries failed.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    last_errors: list[str] = []

    for attempt in range(API_RETRY_COUNT):
        try:
            if attempt > 0 and last_errors:
                # Use retry prompt with error context
                retry_msg = RETRY_PROMPT.format(
                    errors="\n".join(last_errors),
                    min_slides=SLIDE_COUNT_MIN,
                    max_slides=SLIDE_COUNT_MAX,
                    ast_json=ast_json_str[:50000],  # Truncate for retry
                )
                current_user_msg = retry_msg
            else:
                current_user_msg = user_msg

            logger.info(
                "Calling Claude API (attempt %d/%d, model=%s)",
                attempt + 1, API_RETRY_COUNT, AI_PRIMARY_MODEL,
            )

            model = AI_PRIMARY_MODEL if attempt < 2 else AI_FALLBACK_MODEL

            response = client.messages.create(
                model=model,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
                system=system_msg,
                messages=[
                    {"role": "user", "content": current_user_msg},
                    {"role": "assistant", "content": "["},  # Prefill forces JSON array start
                ],
            )

            # Extract text from response — prepend '[' since we used prefill
            response_text = "["
            for block in response.content:
                if hasattr(block, "text"):
                    response_text += block.text

            # Parse JSON
            slides_data = _extract_json(response_text)
            if slides_data is None:
                last_errors = [f"Failed to parse JSON from response: {response_text[:200]}"]
                logger.warning("JSON parse failed on attempt %d", attempt + 1)
                if attempt < API_RETRY_COUNT - 1:
                    time.sleep(API_RETRY_DELAYS_SEC[attempt])
                continue

            # Validate with Pydantic
            validation_errors = _validate_slide_plan(slides_data)
            if validation_errors:
                last_errors = validation_errors
                logger.warning(
                    "Validation failed on attempt %d: %s",
                    attempt + 1, "; ".join(validation_errors[:3]),
                )
                if attempt < API_RETRY_COUNT - 1:
                    time.sleep(API_RETRY_DELAYS_SEC[attempt])
                continue

            logger.info(
                "AI planner succeeded on attempt %d with %d slides",
                attempt + 1, len(slides_data),
            )
            return slides_data

        except anthropic.RateLimitError:
            logger.warning("Rate limited on attempt %d", attempt + 1)
            last_errors = ["API rate limit exceeded"]
            if attempt < API_RETRY_COUNT - 1:
                time.sleep(API_RETRY_DELAYS_SEC[attempt] * 2)

        except anthropic.APIError as exc:
            logger.warning("API error on attempt %d: %s", attempt + 1, exc)
            last_errors = [f"API error: {exc}"]
            if attempt < API_RETRY_COUNT - 1:
                time.sleep(API_RETRY_DELAYS_SEC[attempt])

        except Exception as exc:
            logger.error("Unexpected error in AI planner: %s", exc)
            last_errors = [f"Unexpected error: {exc}"]
            if attempt < API_RETRY_COUNT - 1:
                time.sleep(API_RETRY_DELAYS_SEC[attempt])

    return None


def _extract_json(text: str) -> list[dict[str, Any]] | None:
    """Extract a JSON array from AI response text.

    Handles responses that may be wrapped in markdown fences or have
    leading/trailing text.

    Args:
        text: Raw response text from the AI.

    Returns:
        Parsed list of dicts, or None if parsing fails.
    """
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence
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
        return None
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in the text
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
    """Validate slide plan data against Pydantic schemas.

    Args:
        slides_data: Raw list of slide dicts from the AI.

    Returns:
        List of validation error messages (empty if all valid).
    """
    errors: list[str] = []

    try:
        slide_items = [SlidePlanItem.model_validate(s) for s in slides_data]
        plan = SlidePlan(slides=slide_items)
        errors = plan.validate_all()
    except Exception as exc:
        errors.append(f"Schema validation error: {exc}")

    return errors


def _maybe_cluster_sections(
    ast_dict: dict[str, Any],
    api_key: str,
    target_count: int,
) -> dict[str, Any]:
    """Cluster sections if there are too many for the target slide count.

    Args:
        ast_dict: Original AST dict.
        api_key: Anthropic API key.
        target_count: Target slide count.

    Returns:
        Modified AST dict with clustered sections, or original if no clustering needed.
    """
    sections = ast_dict.get("sections", [])
    if len(sections) <= MAX_SECTIONS_BEFORE_CLUSTERING:
        return ast_dict

    logger.info(
        "Document has %d sections (> %d), attempting AI clustering",
        len(sections), MAX_SECTIONS_BEFORE_CLUSTERING,
    )

    target_groups = min(target_count - 3, len(sections) // 2)  # Leave room for title/agenda/takeaways
    section_list = "\n".join(f"- {s['heading']}" for s in sections)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        clustering_msg = CLUSTERING_PROMPT.format(
            section_count=len(sections),
            max_slides=SLIDE_COUNT_MAX,
            target_groups=target_groups,
            section_list=section_list,
        )

        response = client.messages.create(
            model=AI_PRIMARY_MODEL,
            max_tokens=2048,
            temperature=0.3,
            messages=[{"role": "user", "content": clustering_msg}],
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        clusters = _extract_json(response_text)
        if clusters and isinstance(clusters, list):
            return _apply_clusters(ast_dict, clusters)

    except Exception as exc:
        logger.warning("Clustering failed, using original sections: %s", exc)

    return ast_dict


def _apply_clusters(
    ast_dict: dict[str, Any],
    clusters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply cluster groupings to the AST sections.

    Args:
        ast_dict: Original AST dict.
        clusters: List of {group_name, sections} dicts from AI.

    Returns:
        Modified AST dict with merged sections per cluster.
    """
    sections_by_heading = {s["heading"]: s for s in ast_dict.get("sections", [])}
    new_sections: list[dict[str, Any]] = []

    for cluster in clusters:
        group_name = cluster.get("group_name", "Section")
        member_headings = cluster.get("sections", [])

        merged_body = ""
        merged_blocks: list[dict] = []

        for heading in member_headings:
            sec = sections_by_heading.pop(heading, None)
            if sec:
                merged_body += sec.get("body", "") + "\n"
                merged_blocks.extend(sec.get("blocks", []))

        if merged_blocks or merged_body.strip():
            new_sections.append({
                "heading": group_name,
                "level": 2,
                "body": merged_body.strip(),
                "blocks": merged_blocks,
            })

    # Add any unclustered sections
    for sec in sections_by_heading.values():
        new_sections.append(sec)

    result = dict(ast_dict)
    result["sections"] = new_sections
    logger.info("Clustered %d sections into %d groups", len(ast_dict["sections"]), len(new_sections))
    return result
