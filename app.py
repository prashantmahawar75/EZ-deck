"""
app.py — Simple web frontend for EZ-Deck MD→PPTX pipeline.

Run:  python app.py
Open: http://localhost:8080
"""

import os
import sys
import tempfile
import logging

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    SLIDE_COUNT_MIN,
    SLIDE_COUNT_MAX,
    SLIDE_COUNT_DEFAULT,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
)
from pipeline import MarkdownToPPTXPipeline

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)

app = FastAPI(title="EZ-Deck", docs_url=None, redoc_url=None)

# Ensure output dir exists
os.makedirs(str(DEFAULT_OUTPUT_DIR), exist_ok=True)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EZ-Deck — MD to PPTX</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }
  .container {
    width: 100%;
    max-width: 640px;
  }
  h1 {
    font-size: 2rem;
    font-weight: 700;
    text-align: center;
    margin-bottom: 0.25rem;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .subtitle {
    text-align: center;
    color: #94a3b8;
    margin-bottom: 2rem;
    font-size: 0.9rem;
  }
  .card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 2rem;
  }
  .drop-zone {
    border: 2px dashed #475569;
    border-radius: 8px;
    padding: 2.5rem 1rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: 1.5rem;
  }
  .drop-zone:hover, .drop-zone.dragover {
    border-color: #60a5fa;
    background: rgba(96, 165, 250, 0.05);
  }
  .drop-zone.has-file {
    border-color: #22c55e;
    background: rgba(34, 197, 94, 0.05);
  }
  .drop-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }
  .drop-text { color: #94a3b8; font-size: 0.9rem; }
  .file-name {
    color: #22c55e;
    font-weight: 600;
    font-size: 1rem;
    word-break: break-all;
  }
  .controls {
    display: flex;
    gap: 1rem;
    align-items: end;
    margin-bottom: 1.5rem;
  }
  .field { flex: 1; }
  .field label {
    display: block;
    font-size: 0.8rem;
    color: #94a3b8;
    margin-bottom: 0.4rem;
    font-weight: 500;
  }
  input[type=range] {
    width: 100%;
    accent-color: #60a5fa;
  }
  .range-val {
    display: inline-block;
    background: #334155;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.85rem;
    min-width: 2.5rem;
    text-align: center;
  }
  button {
    width: 100%;
    padding: 0.85rem;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  .btn-convert {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    color: white;
  }
  .btn-convert:hover { opacity: 0.9; transform: translateY(-1px); }
  .btn-convert:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
  }
  .result {
    margin-top: 1.5rem;
    padding: 1.2rem;
    border-radius: 8px;
    display: none;
  }
  .result.success {
    background: rgba(34, 197, 94, 0.1);
    border: 1px solid #22c55e;
    display: block;
  }
  .result.error {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid #ef4444;
    display: block;
  }
  .result h3 { margin-bottom: 0.5rem; font-size: 1rem; }
  .result.success h3 { color: #22c55e; }
  .result.error h3 { color: #ef4444; }
  .stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
    margin: 0.75rem 0;
    font-size: 0.85rem;
  }
  .stat-item { color: #94a3b8; }
  .stat-item span { color: #e2e8f0; font-weight: 600; }
  .btn-download {
    background: #22c55e;
    color: white;
    margin-top: 0.75rem;
    display: inline-block;
    text-align: center;
    text-decoration: none;
    padding: 0.7rem;
    border-radius: 8px;
    font-weight: 600;
    width: 100%;
  }
  .btn-download:hover { opacity: 0.9; }
  .spinner {
    display: none;
    text-align: center;
    padding: 1rem;
    color: #94a3b8;
  }
  .spinner.active { display: block; }
  .spinner .dots::after {
    content: '';
    animation: dots 1.5s steps(4, end) infinite;
  }
  @keyframes dots {
    0% { content: ''; }
    25% { content: '.'; }
    50% { content: '..'; }
    75% { content: '...'; }
  }
  .warnings {
    margin-top: 0.5rem;
    font-size: 0.8rem;
    color: #fbbf24;
  }
</style>
</head>
<body>
<div class="container">
  <h1>EZ-Deck</h1>
  <p class="subtitle">Upload Markdown → Get Professional PPTX</p>

  <div class="card">
    <div class="drop-zone" id="dropZone">
      <div class="drop-icon">📄</div>
      <div class="drop-text">Drop your <b>.md</b> file here or click to browse</div>
    </div>
    <input type="file" id="fileInput" accept=".md,.markdown,.txt" hidden>

    <div class="controls">
      <div class="field">
        <label>Slide Count: <span class="range-val" id="slideVal">12</span></label>
        <input type="range" id="slideRange" min="SLIDE_MIN" max="SLIDE_MAX" value="12">
      </div>
    </div>

    <button class="btn-convert" id="convertBtn" disabled>Convert to PPTX</button>

    <div class="spinner" id="spinner">
      ⚡ Converting<span class="dots"></span>
    </div>

    <div class="result" id="result"></div>
  </div>
</div>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const slideRange = document.getElementById('slideRange');
const slideVal = document.getElementById('slideVal');
const convertBtn = document.getElementById('convertBtn');
const spinner = document.getElementById('spinner');
const resultDiv = document.getElementById('result');
let selectedFile = null;

// Slide range
slideRange.min = SLIDE_MIN;
slideRange.max = SLIDE_MAX;
slideRange.addEventListener('input', () => slideVal.textContent = slideRange.value);

// Drop zone
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f) selectFile(f);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) selectFile(fileInput.files[0]); });

function selectFile(f) {
  selectedFile = f;
  dropZone.classList.add('has-file');
  dropZone.innerHTML = '<div class="drop-icon">✅</div><div class="file-name">' + f.name + '</div><div class="drop-text" style="margin-top:0.3rem">' + (f.size/1024).toFixed(1) + ' KB — click to change</div>';
  convertBtn.disabled = false;
  resultDiv.className = 'result';
  resultDiv.innerHTML = '';
}

// Convert
convertBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  convertBtn.disabled = true;
  spinner.classList.add('active');
  resultDiv.className = 'result';
  resultDiv.innerHTML = '';

  const fd = new FormData();
  fd.append('file', selectedFile);
  fd.append('slides', slideRange.value);

  try {
    const res = await fetch('/convert', { method: 'POST', body: fd });
    const data = await res.json();

    if (data.success) {
      resultDiv.className = 'result success';
      resultDiv.innerHTML = `
        <h3>✅ Conversion Complete</h3>
        <div class="stats">
          <div class="stat-item">Slides: <span>${data.slide_count}</span></div>
          <div class="stat-item">Quality: <span>${data.quality_score}</span></div>
          <div class="stat-item">Time: <span>${data.total_time}</span></div>
          <div class="stat-item">Status: <span>${data.status}</span></div>
        </div>
        ${data.warnings ? '<div class="warnings">⚠ ' + data.warnings + '</div>' : ''}
        <a class="btn-download" href="/download/${data.filename}" download>⬇ Download PPTX</a>
      `;
    } else {
      resultDiv.className = 'result error';
      resultDiv.innerHTML = '<h3>❌ Conversion Failed</h3><p style="color:#94a3b8;font-size:0.9rem">' + (data.error || 'Unknown error') + '</p>';
    }
  } catch (err) {
    resultDiv.className = 'result error';
    resultDiv.innerHTML = '<h3>❌ Network Error</h3><p style="color:#94a3b8;font-size:0.9rem">' + err.message + '</p>';
  }

  spinner.classList.remove('active');
  convertBtn.disabled = false;
});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the single-page frontend."""
    page = HTML_PAGE.replace("SLIDE_MIN", str(SLIDE_COUNT_MIN))
    page = page.replace("SLIDE_MAX", str(SLIDE_COUNT_MAX))
    return page


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    slides: int = Form(default=SLIDE_COUNT_DEFAULT),
):
    """Convert an uploaded markdown file to PPTX.

    Args:
        file: Uploaded .md file.
        slides: Target slide count (10-15).

    Returns:
        JSON with conversion results.
    """
    # Validate file
    if not file.filename:
        return {"success": False, "error": "No file uploaded"}

    # Clamp slide count
    slides = max(SLIDE_COUNT_MIN, min(SLIDE_COUNT_MAX, slides))

    # Save uploaded file to temp location
    try:
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            return {"success": False, "error": "File too large (max 5 MB)"}

        with tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="wb"
        ) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

    except Exception as e:
        logger.error("File upload error: %s", e)
        return {"success": False, "error": f"Upload error: {e}"}

    # Run pipeline
    try:
        pipeline = MarkdownToPPTXPipeline(
            master_path=str(DEFAULT_MASTER_PATH),
            output_dir=str(DEFAULT_OUTPUT_DIR),
            target_slides=slides,
            use_ai=True,
        )
        result = pipeline.run(tmp_path)

        if not result.validation.passed:
            errors = "; ".join(result.validation.errors[:3])
            return {"success": False, "error": f"Pipeline failed: {errors}"}

        filename = os.path.basename(result.output_path)
        return {
            "success": True,
            "filename": filename,
            "slide_count": result.slide_count,
            "quality_score": f"{result.validation.score * 100:.1f}%",
            "total_time": f"{result.timing.get('total_ms', 0)}ms",
            "status": "PASSED" if result.validation.passed else "FAILED",
            "warnings": "; ".join(result.validation.warnings[:3]) if result.validation.warnings else "",
        }

    except Exception as e:
        logger.error("Pipeline error: %s", e)
        return {"success": False, "error": str(e)}

    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.get("/download/{filename}")
async def download(filename: str):
    """Download a generated PPTX file.

    Args:
        filename: Name of the file in the outputs directory.
    """
    # Sanitize filename to prevent path traversal
    safe_name = os.path.basename(filename)
    filepath = os.path.join(str(DEFAULT_OUTPUT_DIR), safe_name)

    if not os.path.exists(filepath):
        return {"error": "File not found"}

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=safe_name,
    )


if __name__ == "__main__":
    import uvicorn
    print("\n  🚀 EZ-Deck Web UI starting at http://localhost:8501\n")
    uvicorn.run(app, host="0.0.0.0", port=8501, log_level="info")
