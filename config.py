"""
config.py — Central configuration for the MD-to-PPTX pipeline.

All constants, thresholds, model names, and tunable parameters live here.
No module should define its own magic numbers — import from config instead.
"""

import os
from pathlib import Path

# ──────────────────────────────────────────────
# Project paths
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"
DEFAULT_MASTER_PATH = ASSETS_DIR / "slide_master.pptx"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"

# ──────────────────────────────────────────────
# Parser thresholds
# ──────────────────────────────────────────────
MAX_INPUT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_LIST_NESTING_DEPTH = 3
MIN_SECTION_WORD_COUNT = 5  # Sections below this are merged with neighbors
MAX_SECTIONS_BEFORE_CLUSTERING = 20

# ──────────────────────────────────────────────
# Planner settings
# ──────────────────────────────────────────────
AI_PRIMARY_MODEL = "claude-sonnet-4-20250514"
AI_FALLBACK_MODEL = "claude-sonnet-4-20250514"
AI_MAX_TOKENS = 8192
AI_TEMPERATURE = 0.4

SLIDE_COUNT_MIN = 10
SLIDE_COUNT_MAX = 15
SLIDE_COUNT_DEFAULT = 12
SLIDE_COUNT_EXTENDED_MIN = 8   # Relaxed range when target can't be met
SLIDE_COUNT_EXTENDED_MAX = 17

API_RETRY_COUNT = 3
API_RETRY_DELAYS_SEC = [2, 4, 8]  # Exponential backoff

# ──────────────────────────────────────────────
# Ollama (local LLM) settings
# ──────────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_REASONING_MODEL = os.environ.get("OLLAMA_REASONING_MODEL", "qwen3:8b")
OLLAMA_GENERATION_MODEL = os.environ.get("OLLAMA_GENERATION_MODEL", "qwen3.5:9b")
OLLAMA_TIMEOUT_SEC = int(os.environ.get("OLLAMA_TIMEOUT_SEC", "300"))
OLLAMA_MAX_TOKENS = 8192
OLLAMA_TEMPERATURE = 0.4
OLLAMA_RETRY_COUNT = 3

# Planner backend: "ollama" | "anthropic" | "fallback"
PLANNER_BACKEND = os.environ.get("PLANNER_BACKEND", "ollama")

VALID_SLIDE_TYPES = [
    "TITLE", "AGENDA", "EXEC_SUMMARY", "CONTENT_BULLETS",
    "CONTENT_TWO_COLUMN", "STAT_HIGHLIGHT", "BAR_CHART",
    "PIE_CHART", "LINE_CHART", "AREA_CHART", "TABLE",
    "TIMELINE_INFOGRAPHIC", "PROCESS_FLOW_INFOGRAPHIC",
    "COMPARISON_INFOGRAPHIC", "KEY_TAKEAWAYS", "SECTION_DIVIDER",
]

# ──────────────────────────────────────────────
# Slide dimensions (standard 16:9 widescreen)
# ──────────────────────────────────────────────
SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5

# Margins & zones as fractions of slide dimensions
MARGIN_LEFT_FRAC = 0.04     # ~0.53 in
MARGIN_RIGHT_FRAC = 0.04
MARGIN_TOP_FRAC = 0.04      # ~0.30 in
MARGIN_BOTTOM_FRAC = 0.04

TITLE_TOP_FRAC = 0.067      # ~0.5 in
TITLE_HEIGHT_FRAC = 0.133   # ~1.0 in
CONTENT_TOP_FRAC = 0.213    # ~1.6 in
CONTENT_HEIGHT_FRAC = 0.72  # ~5.4 in

# ──────────────────────────────────────────────
# Font sizes (in points)
# ──────────────────────────────────────────────
FONT_SIZE_TITLE = 32
FONT_SIZE_SECTION_HEADER = 40
FONT_SIZE_BODY = 18
FONT_SIZE_SMALL = 14
FONT_SIZE_FOOTNOTE = 14         # Raised from 11 → 14 (global readability standard)
FONT_SIZE_STAT_NUMBER = 60
FONT_SIZE_STAT_LABEL = 18
FONT_SIZE_STAT_CONTEXT = 14     # Raised from 12 → 14 (global readability standard)

# ──────────────────────────────────────────────
# Rendering limits
# ──────────────────────────────────────────────
MAX_BULLETS_PER_SLIDE = 6      # 6x6 rule: max 6 lines per slide
MAX_BULLET_WORDS = 7           # 6x6 rule: max 7 words per line (globally accepted)
MAX_WORDS_PER_LINE = 7         # Alias for clarity — same as MAX_BULLET_WORDS
MAX_LINES_PER_SLIDE = 7        # 7x7 rule: max 7 text lines per content area
MAX_STATS_PER_SLIDE = 3
MAX_TIMELINE_EVENTS = 7
MAX_PROCESS_STEPS = 6
MAX_TABLE_COLUMNS = 8
MAX_TABLE_ROWS_PER_SLIDE = 12
MAX_TAKEAWAYS = 5

# ──────────────────────────────────────────────
# Global Presentation Standards (10/20/30 rule + accessibility)
# ──────────────────────────────────────────────
FONT_SIZE_MINIMUM = 14         # 10/20/30 rule: no text below ~14pt for readability
                               # (30pt is for projected slides; 14pt min for tables/footnotes)
IMAGE_HALF_SLIDE_FRAC = 0.50   # Important images should fill >= 50% of usable area
ONE_MINUTE_PER_SLIDE = True    # Design hint: ~1 min of talk time per slide

# ──────────────────────────────────────────────
# Chart rendering
# ──────────────────────────────────────────────
CHART_DPI = 200
CHART_FIGURE_WIDTH = 11
CHART_FIGURE_HEIGHT = 6.5

# ──────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────
MAX_RETRY_COUNT = 2
VALIDATION_PASS_THRESHOLD = 0.7  # Minimum score to not recommend retry

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ──────────────────────────────────────────────
# Custom exceptions
# ──────────────────────────────────────────────
class InputTooLargeError(Exception):
    """Raised when the input markdown file exceeds MAX_INPUT_SIZE_BYTES."""
    pass


class PlannerError(Exception):
    """Raised when the AI planner fails to produce a valid slide plan."""
    pass


class BuildError(Exception):
    """Raised when the PPTX builder encounters an unrecoverable error."""
    pass


class ValidationError(Exception):
    """Raised when the validator detects a critical, unfixable issue."""
    pass
