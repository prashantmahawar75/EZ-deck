#!/usr/bin/env bash
# setup_gcp.sh — One-shot deployment script for EZ-Deck on GCP with local LLMs
# Usage: bash setup_gcp.sh
set -euo pipefail

echo "============================================"
echo "  EZ-Deck GCP Deployment"
echo "  Models: Qwen3:8b + Qwen3.5:9b"
echo "============================================"

PROJECT_DIR="$HOME/EZ-deck"
REPO_URL="https://github.com/prashantmahawar75/EZ-deck.git"

# ── Step 1: Clone or update repo ──
echo ""
echo ">>> Step 1: Clone/update repository"
if [ -d "$PROJECT_DIR" ]; then
    echo "Repository exists, pulling latest..."
    cd "$PROJECT_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

# ── Step 2: Verify Docker & NVIDIA runtime ──
echo ""
echo ">>> Step 2: Verify Docker + GPU"
docker --version
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo "Docker GPU test:"
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || {
    echo "WARNING: Docker GPU test failed. Checking nvidia-container-runtime..."
    # Ensure NVIDIA runtime is configured
    if ! docker info 2>/dev/null | grep -q nvidia; then
        echo "Configuring NVIDIA container runtime..."
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker
        echo "Retrying GPU test..."
        docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader
    fi
}

# ── Step 3: Build and start services ──
echo ""
echo ">>> Step 3: Starting Docker Compose"
cd "$PROJECT_DIR"
docker compose down 2>/dev/null || true
docker compose build --no-cache app
docker compose up -d ollama

# Wait for Ollama to be healthy
echo "Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready!"
        break
    fi
    echo "  Waiting... ($i/60)"
    sleep 5
done

# ── Step 4: Pull models ──
echo ""
echo ">>> Step 4: Pulling LLM models (this takes a while on first run)"
echo "Pulling qwen3:8b..."
docker compose exec -T ollama ollama pull qwen3:8b
echo ""
echo "Pulling qwen3.5:9b..."
docker compose exec -T ollama ollama pull qwen3.5:9b
echo ""
echo "Models available:"
docker compose exec -T ollama ollama list

# ── Step 5: Start the web app ──
echo ""
echo ">>> Step 5: Starting EZ-Deck web app"
docker compose up -d app

# Wait for app
echo "Waiting for app to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8501/ > /dev/null 2>&1; then
        echo "App is ready!"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 3
done

# ── Step 6: Show status ──
echo ""
echo "============================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================"
echo ""
docker compose ps
echo ""
echo "GPU Status:"
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
echo ""

# Get external IP
EXTERNAL_IP=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || echo "unknown")
echo "Access EZ-Deck at:"
echo "  http://localhost:8501"
echo "  http://${EXTERNAL_IP}:8501"
echo ""
echo "Logs: docker compose logs -f"
echo "Stop: docker compose down"
