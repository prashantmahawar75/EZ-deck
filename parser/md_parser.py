"""
parser/md_parser.py — Layer 1: Markdown to structured AST dict.

Uses mistune for tokenization. Handles all edge cases: large files,
missing headings, malformed tables, deep nesting, mixed encoding.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import mistune

from config import (
    MAX_INPUT_SIZE_BYTES,
    MAX_LIST_NESTING_DEPTH,
    InputTooLargeError,
)
from parser.data_detector import detect_data_signals, detect_table_chart_potential

logger = logging.getLogger(__name__)


def parse_markdown(md_path: str) -> dict[str, Any]:
    """Parse a markdown file into a structured AST dictionary.

    Args:
        md_path: Absolute or relative path to the .md file.

    Returns:
        AST dict with keys: title, sections, metadata.

    Raises:
        InputTooLargeError: If the file exceeds MAX_INPUT_SIZE_BYTES.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(md_path)
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    file_size = path.stat().st_size
    if file_size > MAX_INPUT_SIZE_BYTES:
        raise InputTooLargeError(
            f"Input file is {file_size / (1024 * 1024):.1f} MB, "
            f"exceeds limit of {MAX_INPUT_SIZE_BYTES / (1024 * 1024):.0f} MB."
        )

    # Read with encoding fallback
    raw_bytes = path.read_bytes()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decode failed for %s, using errors='replace'", md_path)
        text = raw_bytes.decode("utf-8", errors="replace")

    filename = path.stem  # Used as fallback title

    return _build_ast(text, filename, file_size)


def _build_ast(text: str, filename: str, file_size: int) -> dict[str, Any]:
    """Build the AST dict from raw markdown text.

    Args:
        text: Decoded markdown content.
        filename: Stem of the source file (used as fallback title).
        file_size: Original file size in bytes.

    Returns:
        Complete AST dictionary.
    """
    # Tokenize with mistune
    md = mistune.create_markdown(renderer=None, plugins=['table'])
    tokens = md(text)

    # Extract sections by splitting on headings
    sections: list[dict[str, Any]] = []
    title: str | None = None
    current_section: dict[str, Any] | None = None

    has_tables = False
    has_numeric_data = False
    has_code_blocks = False
    chart_candidates: list[str] = []

    for token in tokens:
        tok_type = token.get("type", "")

        if tok_type == "heading":
            level = token.get("attrs", {}).get("level", 1)
            heading_text = _extract_text(token)

            # Capture first H1 as title
            if level == 1 and title is None:
                title = heading_text

            # Close previous section
            if current_section is not None:
                sections.append(current_section)

            current_section = {
                "heading": heading_text,
                "level": level,
                "body": "",
                "blocks": [],
            }

        else:
            # If no section yet, create a default one
            if current_section is None:
                current_section = {
                    "heading": filename,
                    "level": 1,
                    "body": "",
                    "blocks": [],
                }

            block = _token_to_block(token)
            if block is not None:
                current_section["blocks"].append(block)
                block_text = _block_text(block)
                current_section["body"] += block_text + "\n"

                # Track metadata flags
                if block["type"] == "table":
                    has_tables = True
                if block["type"] == "code":
                    has_code_blocks = True
                if block.get("data_signals"):
                    has_numeric_data = True
                    chart_candidates.append(current_section["heading"])

    # Close last section
    if current_section is not None:
        sections.append(current_section)

    # Fallback title
    if title is None:
        if sections:
            title = sections[0]["heading"]
        else:
            title = filename
        logger.info("No H1 found; using fallback title: %s", title)

    # Filter empty sections
    non_empty = []
    for sec in sections:
        if sec["blocks"] or sec["body"].strip():
            non_empty.append(sec)
        else:
            logger.debug("Skipping empty section: %s", sec["heading"])
    sections = non_empty

    # Detect data signals at section level
    for sec in sections:
        sec_signals = detect_data_signals(sec["body"])
        if sec_signals:
            has_numeric_data = True
            if sec["heading"] not in chart_candidates:
                chart_candidates.append(sec["heading"])
            # Attach signals to the section's blocks
            for block in sec["blocks"]:
                if not block.get("data_signals"):
                    block_text = _block_text(block)
                    block["data_signals"] = detect_data_signals(block_text)

    word_count = len(text.split())

    return {
        "title": title,
        "sections": sections,
        "metadata": {
            "word_count": word_count,
            "has_tables": has_tables,
            "has_numeric_data": has_numeric_data,
            "has_code_blocks": has_code_blocks,
            "detected_chart_candidates": list(set(chart_candidates)),
            "input_size_bytes": file_size,
        },
    }


def _extract_text(token: dict) -> str:
    """Recursively extract plain text from a mistune token tree.

    Args:
        token: A mistune token dict.

    Returns:
        Concatenated plain text from the token and its children.
    """
    if isinstance(token, str):
        return token

    text_parts: list[str] = []

    # Direct text content
    if "raw" in token:
        text_parts.append(token["raw"])
    if "text" in token:
        text_parts.append(token["text"])

    # Children
    children = token.get("children", [])
    if isinstance(children, list):
        for child in children:
            text_parts.append(_extract_text(child))

    return "".join(text_parts).strip()


def _token_to_block(token: dict) -> dict[str, Any] | None:
    """Convert a mistune token into a structured block dict.

    Args:
        token: A mistune token dict.

    Returns:
        A block dict with type, content, and data_signals, or None if
        the token should be skipped.
    """
    tok_type = token.get("type", "")

    if tok_type == "paragraph":
        text = _extract_text(token)
        if not text.strip():
            return None
        return {
            "type": "paragraph",
            "content": text,
            "data_signals": detect_data_signals(text),
        }

    elif tok_type == "list":
        items = _parse_list_items(token, depth=0)
        list_kind = "ordered_list" if token.get("attrs", {}).get("ordered") else "bullet_list"
        full_text = " ".join(_flatten_list_text(items))
        return {
            "type": list_kind,
            "content": items,
            "data_signals": detect_data_signals(full_text),
        }

    elif tok_type == "block_code":
        raw = token.get("raw", token.get("text", ""))
        attrs = token.get("attrs", {})
        lang = attrs.get("info", None) if isinstance(attrs, dict) else None
        return {
            "type": "code",
            "content": {
                "language": lang,
                "code": raw,
            },
            "data_signals": [],
        }

    elif tok_type == "table":
        return _parse_table_token(token)

    elif tok_type == "block_quote":
        text = _extract_text(token)
        return {
            "type": "blockquote",
            "content": text,
            "data_signals": detect_data_signals(text),
        }

    elif tok_type == "block_html":
        # Attempt to extract image references from HTML
        raw = token.get("raw", "")
        if "<img" in raw.lower():
            return {
                "type": "image_ref",
                "content": raw,
                "data_signals": [],
            }
        # Otherwise treat as paragraph
        return {
            "type": "paragraph",
            "content": raw,
            "data_signals": [],
        }

    elif tok_type == "thematic_break":
        return None  # Horizontal rules are structural, not content

    else:
        # Unknown block types: extract text if possible
        text = _extract_text(token)
        if text.strip():
            return {
                "type": "paragraph",
                "content": text,
                "data_signals": detect_data_signals(text),
            }
        return None


def _parse_list_items(token: dict, depth: int) -> list[dict[str, Any]]:
    """Recursively parse list items, flattening beyond MAX_LIST_NESTING_DEPTH.

    Args:
        token: A mistune list token.
        depth: Current nesting depth (0-indexed).

    Returns:
        List of item dicts with "text" and optional "children" keys.
    """
    items: list[dict[str, Any]] = []
    children = token.get("children", [])
    if not isinstance(children, list):
        return items

    for child in children:
        if child.get("type") == "list_item":
            item_text_parts: list[str] = []
            sub_items: list[dict[str, Any]] = []

            for sub in child.get("children", []):
                if sub.get("type") == "list" and depth < MAX_LIST_NESTING_DEPTH - 1:
                    sub_items = _parse_list_items(sub, depth + 1)
                elif sub.get("type") == "list" and depth >= MAX_LIST_NESTING_DEPTH - 1:
                    # Flatten: extract text from nested lists
                    flat_text = _extract_text(sub)
                    if flat_text:
                        item_text_parts.append(flat_text)
                    logger.debug("Flattening nested list at depth %d", depth)
                else:
                    item_text_parts.append(_extract_text(sub))

            item: dict[str, Any] = {"text": " ".join(item_text_parts).strip()}
            if sub_items:
                item["children"] = sub_items
            items.append(item)

    return items


def _flatten_list_text(items: list[dict[str, Any]]) -> list[str]:
    """Flatten nested list items into a flat list of strings.

    Args:
        items: Parsed list items from _parse_list_items.

    Returns:
        Flat list of text strings.
    """
    result: list[str] = []
    for item in items:
        result.append(item.get("text", ""))
        if "children" in item:
            result.extend(_flatten_list_text(item["children"]))
    return result


def _parse_table_token(token: dict) -> dict[str, Any] | None:
    """Parse a mistune table token into a structured table block.

    Degrades to a bullet list if the table is malformed.

    Args:
        token: A mistune table token.

    Returns:
        A table or bullet_list block dict.
    """
    try:
        children = token.get("children", [])
        headers: list[str] = []
        rows: list[list[str]] = []

        for child in children:
            child_type = child.get("type", "")
            if child_type == "table_head":
                # table_head directly contains table_cell children
                for cell_token in child.get("children", []):
                    if cell_token.get("type") == "table_cell":
                        headers.append(_extract_text(cell_token))
            elif child_type == "table_body":
                for row_token in child.get("children", []):
                    row: list[str] = []
                    for cell_token in row_token.get("children", []):
                        if cell_token.get("type") == "table_cell":
                            row.append(_extract_text(cell_token))
                    if row:
                        rows.append(row)

        if not headers:
            raise ValueError("Table has no headers")

        # Detect chart potential for this table
        chart_signal = detect_table_chart_potential(headers, rows)
        data_signals = [chart_signal] if chart_signal else []

        return {
            "type": "table",
            "content": {
                "headers": headers,
                "rows": rows,
            },
            "data_signals": data_signals,
        }

    except Exception as exc:
        logger.warning("Malformed table, degrading to bullet list: %s", exc)
        text = _extract_text(token)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return {
            "type": "bullet_list",
            "content": [{"text": line} for line in lines],
            "data_signals": [],
        }


def _block_text(block: dict[str, Any]) -> str:
    """Extract displayable text from a parsed block.

    Args:
        block: A block dict produced by _token_to_block.

    Returns:
        Plain text representation of the block.
    """
    btype = block["type"]
    content = block["content"]

    if btype in ("paragraph", "blockquote", "image_ref"):
        return content if isinstance(content, str) else str(content)

    elif btype in ("bullet_list", "ordered_list"):
        if isinstance(content, list):
            return " ".join(_flatten_list_text(content))
        return str(content)

    elif btype == "code":
        if isinstance(content, dict):
            return content.get("code", "")
        return str(content)

    elif btype == "table":
        if isinstance(content, dict):
            parts = list(content.get("headers", []))
            for row in content.get("rows", []):
                parts.extend(row)
            return " ".join(parts)
        return str(content)

    return str(content)
