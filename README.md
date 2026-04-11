# EZ-Deck — Markdown to PowerPoint Pipeline

> **An AI-powered, production-grade system that converts Markdown documents into
> visually polished, master-compliant .pptx presentations.**

EZ-Deck transforms unstructured Markdown content into compelling slide decks by
combining intelligent content analysis with professional layout design. The system
uses a 5-layer architecture — Parser, AI Planner, Renderers, PPTX Builder, and
QA Validator — to produce presentations that respect your corporate Slide Master
theme, include data-driven charts, and follow presentation design best practices.

Unlike simple bullet-dump tools, EZ-Deck creates **coherent narratives**: it detects
numeric data for automatic chart generation, groups related sections, synthesizes
executive summaries, and ensures every slide follows the 5-bullet/12-word rule.
The AI planner (powered by Claude) creates a strategic presentation flow, while the
rule-based fallback ensures the system works even without an API key.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| pip | Latest |
| ANTHROPIC_API_KEY | Optional (enables AI planner) |
| Slide Master file | Any .pptx template |

---

## Setup

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd md_to_pptx
```

### 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

> **Note:** The AI planner is optional. Without an API key, the system
> automatically falls back to a deterministic rule-based planner.

### 5. Add your Slide Master

Place your corporate `.pptx` template at `assets/slide_master.pptx`. The system
extracts theme colors, fonts, and layouts from this file to ensure brand compliance.

---

## Usage

### Basic usage

```bash
python main.py --input document.md --master assets/slide_master.pptx
```

### Full options

```bash
python main.py \
  --input path/to/document.md \
  --master assets/slide_master.pptx \
  --output outputs/ \
  --slides 12 \
  --verbose \
  --no-ai
```

| Flag | Description | Default |
|---|---|---|
| `--input, -i` | Path to Markdown file | *required* |
| `--master, -m` | Path to Slide Master .pptx | *required* |
| `--output, -o` | Output directory | `./outputs` |
| `--slides, -s` | Target slide count (10–15) | 12 |
| `--verbose, -v` | Detailed logging | Off |
| `--no-ai` | Skip AI planner, use rules only | Off |

### Example output

```
══════════════════════════════════════════════════
  EZ-Deck — Markdown to PowerPoint Pipeline
══════════════════════════════════════════════════
  Input:  quarterly_report.md
  Master: assets/slide_master.pptx
  Target: 12 slides
  Mode:   AI-powered
──────────────────────────────────────────────────
  PIPELINE RESULTS
  Output:  outputs/quarterly_report.pptx
  Slides:  12
  Score:   92.5%
  Status:  PASSED
  Parse:   45ms
  Plan:    3200ms
  Build:   1800ms
  Total:   5045ms
──────────────────────────────────────────────────
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI (main.py)                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  Pipeline Orchestrator                       │
│                    (pipeline.py)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │  Layer 1  │ │  Layer 2  │ │  Layer 3  │ │   Layer 4     │   │
│  │  Parser   │→│ AI Plan  │→│ Render   │→│  PPTX Build   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│                                              │               │
│                              ┌───────────────▼──────────┐   │
│                              │      Layer 5              │   │
│                              │    QA Validator           │   │
│                              │  (auto-retry if needed)   │   │
│                              └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1 — Parser (`parser/`)
- Tokenizes Markdown using **mistune**
- Detects data patterns (currencies, percentages, year-series)
- Produces a structured AST dict with metadata

### Layer 2 — AI Planner (`planner/`)
- Calls **Claude API** with structured prompts
- Validates output against **Pydantic** schemas
- Self-heals by feeding validation errors back to the AI
- Falls back to rule-based planner if API is unavailable

### Layer 3 — Renderers (`renderers/`)
- **chart_renderer.py** — matplotlib charts (bar, pie, line, area)
- **infographic_renderer.py** — native-shape timelines, process flows, comparisons
- **table_renderer.py** — themed tables with alternating rows
- **content_renderer.py** — bullets, stats, titles, dividers

### Layer 4 — PPTX Builder (`builder/`)
- Loads Slide Master and extracts theme (colors, fonts)
- Maps slide types to master layouts
- Assembles final .pptx using python-pptx

### Layer 5 — Validator (`validator/`)
- 8 quality checks: integrity, count, coverage, overflow, charts, accessibility
- Weighted scoring (0.0–1.0)
- Auto-retry with hints fed back to the planner

---

## Key Design Decisions

### Why AI Planner over Rule-Based?
The AI planner creates **coherent narratives** — it groups related sections,
identifies the best slide type for each piece of content, and ensures a logical
flow. The rule-based fallback produces functional but mechanical output:
correct structure, but without narrative craft.

### Why python-pptx over API-based Tools?
python-pptx gives us **direct master compliance** — we read the actual XML
theme from your Slide Master, extract colors and fonts, and apply them to
every element. No watermarks, no internet dependency, fully offline.

### Why matplotlib over Native PPTX Charts?
python-pptx's chart support is limited and doesn't give us fine control over
visual style (custom colors, transparent backgrounds, grid lines). matplotlib
gives us **pixel-perfect** charts that match the master theme.

### Why Pydantic for Slide Plans?
Pydantic provides **self-healing validation**: when the AI returns malformed
JSON, we catch the exact error and feed it back to the AI with an error-correction
prompt. This dramatically improves first-pass success rates.

### Why 5-Layer Separation?
Each layer is independently testable and replaceable. You can swap the AI
planner for a different LLM, change the chart library, or add new slide types
without touching the other layers.

---

## Edge Case Handling

| Case | Behavior |
|---|---|
| Input > 5MB | `InputTooLargeError` with clear message |
| No headings | Uses filename as title, treats doc as one section |
| Malformed table | Degrades to bullet list, logs warning |
| Deep nesting (>3 levels) | Flattens to 3 levels max |
| >20 sections | AI clusters related sections before planning |
| No numeric data | Skips chart slides, uses more content/infographic slides |
| API rate limit | Exponential backoff (2s/4s/8s) + fallback planner |
| Missing API key | Immediate fallback to rule-based planner |
| No master layouts | Uses first available layout with title placeholder |
| Large table (>20 rows) | Paginates across multiple slides |
| Empty sections | Skipped with DEBUG log |
| Mixed encoding | `errors='replace'` with warning |

---

## Known Limitations

1. **LaTeX/Math**: Rendered as plain text with a "formula" label — no
   actual equation rendering
2. **Images**: Image references in Markdown are detected but not embedded
   in the output (the source images would need to be bundled)
3. **Code blocks**: Displayed as key-point slides rather than syntax-highlighted
   code (PPTX has no native code rendering)
4. **Slide Master compatibility**: Works best with standard PowerPoint masters;
   custom XML schemas may need manual layout index adjustment
5. **Chart data accuracy**: The AI planner infers chart data from text — verify
   critical numbers match the source document

---

## Project Structure

```
md_to_pptx/
├── main.py                       # CLI entry point
├── pipeline.py                   # Orchestrator
├── config.py                     # Constants & custom exceptions
├── parser/
│   ├── md_parser.py              # Markdown → AST
│   └── data_detector.py          # Numeric pattern detection
├── planner/
│   ├── ai_planner.py             # Claude API integration
│   ├── fallback_planner.py       # Rule-based fallback
│   ├── slide_plan_schema.py      # Pydantic validation models
│   └── prompts.py                # AI prompt templates
├── renderers/
│   ├── chart_renderer.py         # matplotlib charts
│   ├── infographic_renderer.py   # Native shape infographics
│   ├── table_renderer.py         # Themed tables
│   └── content_renderer.py       # Text-based slides
├── builder/
│   ├── pptx_builder.py           # PPTX assembly
│   ├── slide_factory.py          # Slide type dispatch
│   ├── layout_manager.py         # Master layout selection
│   └── style_constants.py        # Theme extraction
├── validator/
│   └── pptx_validator.py         # Quality checks
├── assets/
│   └── slide_master.pptx         # Your template
├── outputs/                      # Generated files
├── requirements.txt
└── README.md
```

---

## License

MIT — see LICENSE for details.
