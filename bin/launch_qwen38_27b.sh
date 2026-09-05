#!/usr/bin/env bash
# ==============================================================================
# Qwen 3.8 27B Server Launcher for 16GB VRAM GPUs
# Launches llama-server on port 8034 with 3 Continuous Batching Slots:
#   Slot 1: 👑 Chief Orchestrator
#   Slot 2: 🔍 Symbol & AST Scout Sub-Agent
#   Slot 3: ⚙️ Pi Dev Draftsman Sub-Agent
# ==============================================================================

set -e

PORT=${SWARM_LFM_PORT:-8034}
HOST="0.0.0.0"
MODELS_DIR="$HOME/models"
MODEL_PATH="$MODELS_DIR/qwen-3.8-27b-coder-q4_k_s.gguf"
KV_CACHE_DIR="$HOME/.swarm/kv_cache"

mkdir -p "$MODELS_DIR"
mkdir -p "$KV_CACHE_DIR"

# Locate llama-server binary
LLAMA_SERVER=""
CANDIDATE_PATHS=(
    "/home/shawry/llama-cpp-tq4/build/bin/llama-server"
    "$HOME/llama-cpp-tq4/build/bin/llama-server"
    "$HOME/llama.cpp/build/bin/llama-server"
    "$(which llama-server 2>/dev/null || true)"
)

for cand in "${CANDIDATE_PATHS[@]}"; do
    if [[ -n "$cand" && -x "$cand" ]]; then
        LLAMA_SERVER="$cand"
        break
    fi
done

if [[ -z "$LLAMA_SERVER" ]]; then
    echo "❌ Error: Could not find 'llama-server' executable."
    echo "Please build llama.cpp or ensure llama-server is on your PATH."
    exit 1
fi

echo "=================================================================="
echo "🚀 Swarm AI Studio — Qwen 3.8 27B Local GPU Launcher (16GB VRAM)"
echo "=================================================================="
echo " • Engine Binary:   $LLAMA_SERVER"
echo " • Model File:      $MODEL_PATH"
echo " • Port:            http://$HOST:$PORT"
echo " • Slots:           3 (1 Orchestrator + 2 Sub-Agents)"
echo " • Acceleration:    FlashAttention-2 + Continuous Batching"
echo " • KV Cache:        Quantized Q8 + Adaptive Streaming"
echo "=================================================================="

# Check if model exists, if not prompt / trigger downloader
if [[ ! -f "$MODEL_PATH" ]]; then
    # Check fallback names
    if [[ -f "$HOME/Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf" ]]; then
        echo "ℹ️ Using existing local Qwen model: $HOME/Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf"
        MODEL_PATH="$HOME/Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf"
    else
        echo "📥 Qwen 3.8 27B model not found locally at $MODEL_PATH."
        echo "Starting automated download via scripts/download_qwen38_27b.py..."
        python3 "$(dirname "$0")/../scripts/download_qwen38_27b.py"
    fi
fi

# Kill any existing server on the port
PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [[ -n "$PID" ]]; then
    echo "⚠️ Stopping existing process on port $PORT (PID $PID)..."
    kill -9 $PID 2>/dev/null || true
    sleep 1
fi

echo "⚡ Launching Qwen 3.8 27B continuous batching server..."
exec "$LLAMA_SERVER" \
    -m "$MODEL_PATH" \
    --port "$PORT" \
    --host "$HOST" \
    -ngl 99 \
    -np 3 \
    -c 16384 \
    --cont-batching \
    -fa on \
    -ctk q8_0 \
    -ctv q8_0 \
    --slot-save-path "$KV_CACHE_DIR" \
    -ub 512 \
    -b 2048 \
    --metrics \
    --threads 8
