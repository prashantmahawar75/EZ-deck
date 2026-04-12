"""Diagnostic script: capture raw Ollama response for complex doc."""
import requests
import json
import sys

OLLAMA_URL = "http://ollama:11434/api/chat"

# Read test file
try:
    with open("samples/dynamic_ecommerce/test_dynamic.md") as f:
        content = f.read()
except FileNotFoundError:
    print("test_dynamic.md not found, using inline test")
    content = "# Test\n## Section 1\nData: Revenue $1M, Growth 25%\n| Q | Revenue |\n|---|---|\n| Q1 | 200K |\n| Q2 | 300K |"

print(f"Document length: {len(content)} chars")

resp = requests.post(OLLAMA_URL, json={
    "model": "qwen3.5:27b",
    "messages": [
        {"role": "system", "content": "Output ONLY a valid JSON array of slide objects. No markdown fences, no explanation. Start with [ end with ]."},
        {"role": "user", "content": f"Generate a JSON slide plan (10-12 slides) for this document. Each slide: slide_number, slide_type, title, content, speaker_notes.\n\nDocument:\n{content[:3000]}"}
    ],
    "stream": False,
    "think": False,
    "options": {"temperature": 0.3, "num_predict": 8192, "num_ctx": 16384}
}, timeout=300)

data = resp.json()
msg = data.get("message", {})
raw = msg.get("content", "")
thinking = msg.get("thinking", "")

print(f"\n=== THINKING length: {len(thinking)}")
if thinking:
    print(f"THINKING first 300: {repr(thinking[:300])}")

print(f"\n=== CONTENT length: {len(raw)}")
print(f"=== CONTENT first 500: {repr(raw[:500])}")
print(f"=== CONTENT last 500: {repr(raw[-500:])}")
print(f"=== DONE_REASON: {data.get('done_reason')}")
print(f"=== EVAL_COUNT: {data.get('eval_count')}")

# Try parsing
try:
    parsed = json.loads(raw)
    print(f"\n=== JSON PARSE: SUCCESS, type={type(parsed).__name__}, len={len(parsed) if isinstance(parsed, list) else 'N/A'}")
except json.JSONDecodeError as e:
    print(f"\n=== JSON PARSE ERROR: {e}")
    # Try bracket extraction
    start = raw.find("[")
    end = raw.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start:end+1])
            print(f"=== BRACKET EXTRACT: SUCCESS, len={len(parsed)}")
        except json.JSONDecodeError as e2:
            print(f"=== BRACKET EXTRACT FAILED: {e2}")
            # Show around the error position
            pos = e2.pos if hasattr(e2, 'pos') else e.pos
            snippet = raw[max(0,pos-100):pos+100]
            print(f"=== AROUND ERROR POS {pos}: {repr(snippet)}")
