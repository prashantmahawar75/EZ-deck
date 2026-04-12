# EZ-Deck Architecture & Setup Guide

> **Production-Grade Markdown → PowerPoint Pipeline**

---

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Detailed Setup](#detailed-setup)
6. [Running the Application](#running-the-application)
7. [API Reference](#api-reference)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           EZ-Deck Pipeline                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐ │
│   │  INPUT  │───▶│ PARSER  │───▶│ PLANNER │───▶│ BUILDER │───▶│ OUTPUT  │ │
│   │   .md   │    │  Layer  │    │  Layer  │    │  Layer  │    │  .pptx  │ │
│   └─────────┘    └────┬────┘    └────┬────┘    └────┬────┘    └─────────┘ │
│                       │              │              │                      │
│                       ▼              ▼              ▼                      │
│              ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│              │   md_parser │ │  AI Planner │ │ pptx_builder│              │
│              │   insights  │ │   (Ollama)  │ │   renderers │              │
│              │   detector  │ │  or Fallback│ │   validator │              │
│              └─────────────┘ └─────────────┘ └─────────────┘              │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘

                              Web UI (FastAPI)
                           ┌──────────────────┐
                           │   http://IP:8501 │
                           │                  │
                           │  Upload .md      │
                           │  Download .pptx  │
                           └──────────────────┘
```

### Pipeline Layers

| Layer | Module | Purpose |
|-------|--------|---------|
| **Parser** | `parser/md_parser.py` | Tokenize markdown, extract structure |
| **Insights** | `parser/insight_engine.py` | Detect data patterns, generate summaries |
| **Data Detector** | `parser/data_detector.py` | Find charts, tables, numeric data |
| **Planner** | `planner/ai_planner.py` | AI-powered slide planning (Claude) |
| **Planner** | `planner/ollama_planner.py` | Local LLM planning (Ollama) |
| **Planner** | `planner/fallback_planner.py` | Rule-based fallback |
| **Builder** | `builder/pptx_builder.py` | PPTX generation orchestrator |
| **Builder** | `builder/slide_factory.py` | Slide creation factory |
| **Builder** | `builder/layout_manager.py` | Layout selection & positioning |
| **Renderers** | `renderers/chart_renderer.py` | Charts (bar, pie, line) |
| **Renderers** | `renderers/content_renderer.py` | Text, bullets, takeaways |
| **Renderers** | `renderers/infographic_renderer.py` | Process flows, timelines, comparisons |
| **Renderers** | `renderers/table_renderer.py` | Themed tables |
| **Validator** | `validator/pptx_validator.py` | Quality scoring (0.0–1.0) |

---

## Project Structure

```
EZ/
├── app.py                  # Web UI (FastAPI) - main entry point
├── main.py                # CLI entry point
├── pipeline.py            # Pipeline orchestrator
├── config.py              # Configuration & environment
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container config
├── docker-compose.yml     # Docker Compose setup
│
├── parser/                # Layer 1: Markdown parsing
│   ├── __init__.py
│   ├── md_parser.py       # Markdown tokenizer
│   ├── insight_engine.py  # Content analysis
│   └── data_detector.py   # Chart/table detection
│
├── planner/               # Layer 2: Slide planning
│   ├── __init__.py
│   ├── ai_planner.py      # Claude AI planner
│   ├── ollama_planner.py  # Local Ollama LLM planner
│   ├── fallback_planner.py # Rule-based fallback
│   ├── prompts.py         # AI prompt templates
│   └── slide_plan_schema.py # Pydantic schemas
│
├── builder/               # Layer 3: PPTX generation
│   ├── __init__.py
│   ├── pptx_builder.py    # Main builder
│   ├── slide_factory.py   # Slide creation
│   ├── layout_manager.py  # Layout handling
│   └── style_constants.py # Design constants
│
├── renderers/             # Slide type renderers
│   ├── __init__.py
│   ├── chart_renderer.py  # Chart generation
│   ├── content_renderer.py # Text rendering
│   ├── infographic_renderer.py # Visual infographics
│   └── table_renderer.py  # Table rendering
│
├── validator/             # Quality assurance
│   ├── __init__.py
│   └── pptx_validator.py  # Validation checks
│
├── assets/                # Static assets
│   └── slide_master.pptx  # Default template
│
├── outputs/               # Generated presentations
├── samples/               # Sample markdown files
│   ├── eval/              # Evaluation test cases
│   ├── short_agenda/
│   ├── long_report/
│   └── dynamic_ecommerce/
│
└── test_outputs/          # Test output directory
```

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.10+ | Core runtime |
| pip | Latest | Package manager |
| Git | 2.x+ | Version control |

### Optional (for AI features)

| Software | Version | Purpose |
|----------|---------|---------|
| Ollama | Latest | Local LLM (recommended) |
| ANTHROPIC_API_KEY | - | Claude AI planner |

### Optional (for PDF export)

| Software | Purpose |
|----------|---------|
| LibreOffice | PDF conversion |
| Poppler | pdf2image support |

---

## Quick Start

### One-liner (Linux/macOS)

```bash
git clone https://github.com/prashantmahawar75/EZ-deck.git && cd EZ-deck && pip install -r requirements.txt && python app.py
```

### Then open: http://localhost:8501

---

## Detailed Setup

### Windows

```powershell
# 1. Clone repository
git clone https://github.com/prashantmahawar75/EZ-deck.git
cd EZ-deck

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. (Optional) Install Ollama for local AI
# Download from: https://ollama.ai/download/windows
# Then pull the model:
ollama pull qwen3:8b

# 5. Run the web app
python app.py
```

### macOS

```bash
# 1. Clone repository
git clone https://github.com/prashantmahawar75/EZ-deck.git
cd EZ-deck

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. (Optional) Install Ollama for local AI
brew install ollama
ollama serve &
ollama pull qwen3:8b

# 5. (Optional) For PDF export
brew install libreoffice
brew install poppler

# 6. Run the web app
python app.py
```

### Linux (Ubuntu/Debian)

```bash
# 1. Install system dependencies
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip git

# 2. Clone repository
git clone https://github.com/prashantmahawar75/EZ-deck.git
cd EZ-deck

# 3. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 5. (Optional) Install Ollama for local AI
curl -fsSL https://ollama.ai/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama
ollama pull qwen3:8b

# 6. (Optional) For PDF export
sudo apt install -y libreoffice poppler-utils

# 7. Run the web app
python app.py
```

### GCP Instance Setup

```bash
# SSH into your instance
gcloud compute ssh INSTANCE_NAME --zone=ZONE

# Clone and setup
git clone https://github.com/prashantmahawar75/EZ-deck.git
cd EZ-deck
pip3 install -r requirements.txt

# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3:8b

# Run (use screen or systemd for persistence)
screen -S ezdeck
python3 app.py

# Or create systemd service (see below)
```

#### Systemd Service (for production)

Create `/etc/systemd/system/ezdeck.service`:

```ini
[Unit]
Description=EZ-Deck Web App
After=network.target ollama.service

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/EZ-deck
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ezdeck
sudo systemctl start ezdeck
```

---

## Running the Application

### Web UI (Recommended)

```bash
python app.py
# Opens at http://localhost:8501
```

**Usage:**
1. Open http://localhost:8501 (or http://YOUR_IP:8501)
2. Drag and drop your `.md` file
3. Adjust slide count (10-15)
4. Click "Convert to PPTX"
5. Download the generated presentation

### CLI

```bash
python main.py --input document.md --slides 12
```

**Full CLI options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--input, -i` | Path to markdown file | *required* |
| `--master, -m` | Path to slide master | `assets/slide_master.pptx` |
| `--output, -o` | Output directory | `outputs/` |
| `--slides, -s` | Target slide count | 12 |
| `--verbose, -v` | Enable debug logging | Off |
| `--no-ai` | Disable AI planner | Off |

### Docker

```bash
# Build and run
docker-compose up --build

# Access at http://localhost:8501
```

---

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web UI (HTML) |
| POST | `/convert` | Convert MD to PPTX |
| GET | `/download/{filename}` | Download generated PPTX |

### POST /convert

**Request:**
- `file`: Uploaded `.md` file (multipart/form-data)
- `slides`: Target slide count (form field, default: 12)

**Response:**
```json
{
  "success": true,
  "filename": "document.pptx",
  "slide_count": 12,
  "quality_score": "92.5%",
  "total_time": "5045ms",
  "status": "PASSED",
  "warnings": ""
}
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PLANNER_BACKEND` | `anthropic`, `ollama`, or `fallback` | `ollama` |
| `ANTHROPIC_API_KEY` | Claude API key | - |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_REASONING_MODEL` | Model for planning | `qwen3:8b` |
| `OLLAMA_PLAN_TIMEOUT` | Planning timeout (seconds) | 300 |

### config.py Settings

```python
# Slide constraints
SLIDE_COUNT_MIN = 10
SLIDE_COUNT_MAX = 15
SLIDE_COUNT_DEFAULT = 12

# Quality thresholds
MIN_QUALITY_SCORE = 0.70

# File paths
DEFAULT_MASTER_PATH = "assets/slide_master.pptx"
DEFAULT_OUTPUT_DIR = "outputs"
```

---

## Troubleshooting

### Common Issues

#### "Port 8501 already in use"
```bash
# Find process using port
lsof -i :8501  # macOS/Linux
netstat -ano | findstr :8501  # Windows

# Kill the process
kill -9 PID  # macOS/Linux
taskkill /PID PID /F  # Windows
```

#### "Ollama connection refused"
```bash
# Check if Ollama is running
ollama list

# Start Ollama
ollama serve  # macOS/Linux
# Or start Ollama app on Windows/macOS
```

#### "No module named 'xxx'"
```bash
# Ensure virtual environment is activated
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate  # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

#### "Permission denied" (Linux)
```bash
# Run with proper user permissions
sudo chown -R $USER:$USER /path/to/EZ-deck
```

#### Firewall Issues (GCP)
```bash
# Create firewall rule for port 8501
gcloud compute firewall-rules create allow-ezdeck-8501 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:8501 \
  --source-ranges=0.0.0.0/0
```

---

## Deployment URLs

| Environment | URL |
|-------------|-----|
| Local | http://localhost:8501 |
| GCP Instance | http://34.87.144.173:8501 |

---

## Tech Stack

- **Backend**: FastAPI, Uvicorn
- **Frontend**: Embedded HTML/CSS/JS (single-page)
- **PPTX**: python-pptx
- **Charts**: matplotlib
- **AI**: Ollama (qwen3:8b), Anthropic Claude
- **Validation**: Pydantic

---

## License

MIT License

---

*Last updated: April 2026*
