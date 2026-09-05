#!/usr/bin/env bash
# ==============================================================================
# Qwen / Local LLM Unified Server Launcher
# Hardware Target: AMD Ryzen 7 8845HS (16T) · RTX 5070 Ti (16GB VRAM) · 32GB RAM
# Optimized for: Pi / GSD2 / Multi-Agent Parallel Slot Inference
# ==============================================================================
# Usage:
#   ./qwen.sh [CHOICE] [extra llama-server flags...]
#
# Examples:
#   ./qwen.sh 1                    # Launch Qwen 3.8 27B (Full GPU, MTP Drafter, 4 slots)
#   ./qwen.sh 2                    # Launch Qwen 3.6 35B A3B Q6_K_XL (Hybrid, 2 slots) [Default]
#   ./qwen.sh 3                    # Launch Qwen 3.6 35B A3B Q4_K_M (Hybrid, 2 slots)
#   ./qwen.sh 4                    # Launch Qwen 3.5 9B Q8_0 (Full GPU, 131k ctx, 4 slots)
#   ./qwen.sh 5 /path/to/model.gguf # Launch custom model
#   ./qwen.sh --help               # Show help & configuration options
#
# Environment Variable Overrides:
#   HOST, PORT, PARALLEL, CTX_SIZE, CTK, CTV, NGL, KV_CACHE_DIR,
#   LLAMA_SERVER_BIN, CACHE_REUSE, REASONING_BUDGET, TEMP, TOP_P, TOP_K
# ==============================================================================

set -euo pipefail

# ── Color Support ─────────────────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  BOLD=$'\e[1m'
  DIM=$'\e[2m'
  RESET=$'\e[0m'
  RED=$'\e[1;31m'
  GREEN=$'\e[1;32m'
  YELLOW=$'\e[1;33m'
  BLUE=$'\e[1;34m'
  MAGENTA=$'\e[1;35m'
  CYAN=$'\e[1;36m'
  WHITE=$'\e[1;37m'
else
  BOLD=""
  DIM=""
  RESET=""
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  MAGENTA=""
  CYAN=""
  WHITE=""
fi

# ── Global Environment Defaults ───────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8033}"
KV_CACHE_DIR="${KV_CACHE_DIR:-${SLOT_SAVE_PATH:-/home/shawry/.gsd/kv_cache}}"
CACHE_REUSE="${CACHE_REUSE:-256}"
REASONING_BUDGET="${REASONING_BUDGET:-4096}"
BATCH_SIZE="${BATCH_SIZE:-2048}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
TEMP="${TEMP:-0.6}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-20}"
MIN_P="${MIN_P:-0.0}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-0.5}"
REPEAT_PENALTY="${REPEAT_PENALTY:-1.0}"

# Base directories
MODELS_DIR="${MODELS_DIR:-/home/shawry/models}"
HF_CACHE_DIR="${HF_CACHE_DIR:-/home/shawry/.cache/huggingface/hub}"

# ── Helper: Show Help ─────────────────────────────────────────────────────────
show_help() {
  cat <<EOF
${BOLD}Qwen / Local LLM Server Launcher for Pi / GSD2${RESET}

${CYAN}Usage:${RESET}
  ./qwen.sh [OPTION] [EXTRA_LLAMA_SERVER_FLAGS...]

${CYAN}Available Models:${RESET}
  ${GREEN}1)${RESET} ${BOLD}Qwen 3.8 27B UD-Q3_K_XL${RESET} (12.2 GB)
     • 100% GPU VRAM offload (ngl 99) · 2 Concurrent Slots · 32K Context (~16K/slot)
     • Fused Gated Delta Net (Chunked) · Full GPU (~50-75 t/s)
  ${GREEN}2)${RESET} ${BOLD}Qwen 3.6 35B A3B UD-Q6_K_XL${RESET} (31.0 GB) ${YELLOW}[Default]${RESET}
     • Hybrid GPU/CPU offload (ngl 15) · 2 Concurrent Slots · 32K Context
     • High Precision MoE (~15-25 t/s)
  ${GREEN}3)${RESET} ${BOLD}Qwen 3.6 35B A3B UD-Q4_K_M${RESET} (21.0 GB)
     • Hybrid GPU/CPU offload (ngl 22) · 2 Concurrent Slots · 32K Context
     • Balanced MoE (~25-35 t/s)
  ${GREEN}4)${RESET} ${BOLD}Qwen 3.5 9B Q8_0${RESET} (8.9 GB)
     • 100% GPU VRAM offload (ngl 99) · 4 Concurrent Slots · 65K Context
     • Ultra Fast (~80-120 t/s) · Large Context Testing
  ${GREEN}5)${RESET} ${BOLD}Custom Model${RESET}
     • Supply custom GGUF model path directly or interactively

${CYAN}Environment Variable Overrides:${RESET}
  PORT              Server listening port (default: 8033)
  HOST              Server host bind address (default: 0.0.0.0)
  PARALLEL          Number of concurrent request slots (default: 2 for 27B/35B, 4 for 9B)
  CTX_SIZE          Total allocated context tokens across slots (default: 32768 or 65536)
  CTK, CTV          KV cache quantization format for Key/Value (default: q8_0)
  NGL               GPU layers to offload (default: model-optimized)
  KV_CACHE_DIR      Directory to persist slot KV state (default: /home/shawry/.gsd/kv_cache)
  CACHE_REUSE       Prefix cache chunk reuse threshold (default: 256)
  REASONING_BUDGET  Max tokens allocated for reasoning thoughts (default: 4096)
  LLAMA_SERVER_BIN  Path to custom llama-server binary

${CYAN}Examples:${RESET}
  ./qwen.sh 1
  ./qwen.sh 2 --port 8080
  PARALLEL=1 CTX_SIZE=32768 ./qwen.sh 2
EOF
}

# ── Helper: Locate llama-server Binary ─────────────────────────────────────────
find_llama_server() {
  if [[ -n "${LLAMA_SERVER_BIN:-}" && -x "$LLAMA_SERVER_BIN" ]]; then
    echo "$LLAMA_SERVER_BIN"
    return 0
  fi

  local candidates=(
    "/home/shawry/llama-cpp-tq4/build/bin/llama-server"
    "/home/shawry/llama.cpp-mtp/build/bin/llama-server"
    "/home/shawry/llama.cpp-tq3/build/bin/llama-server"
    "/home/shawry/llama.cpp/build/bin/llama-server"
    "/home/shawry/llamaserver/llama-server"
    "/usr/local/bin/llama-server"
    "/opt/llama.cpp/bin/llama-server"
  )

  for bin in "${candidates[@]}"; do
    if [[ -x "$bin" ]]; then
      echo "$bin"
      return 0
    fi
  done

  if command -v llama-server >/dev/null 2>&1; then
    command -v llama-server
    return 0
  fi

  return 1
}

# ── Helper: First Existing File ───────────────────────────────────────────────
find_first_existing() {
  for file in "$@"; do
    if [[ -f "$file" ]]; then
      echo "$file"
      return 0
    fi
  done
  echo "$1"
  return 1
}

# ── Parse Initial Arguments ───────────────────────────────────────────────────
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
  exit 0
fi

# ── Locate Server Binary ──────────────────────────────────────────────────────
SERVER_BIN="$(find_llama_server || true)"
if [[ -z "$SERVER_BIN" || ! -x "$SERVER_BIN" ]]; then
  echo -e "${RED}❌ Error: llama-server binary not found.${RESET}"
  echo -e "   Please compile llama.cpp or set ${BOLD}LLAMA_SERVER_BIN=/path/to/llama-server${RESET}."
  exit 1
fi

# ── Model Path Resolution ─────────────────────────────────────────────────────
QWEN38_MODEL="$(find_first_existing \
  "$MODELS_DIR/Qwen3.8-27B-UD-Q3_K_XL.gguf" \
  "/home/shawry/Qwen3.8-27B-UD-Q3_K_XL.gguf" \
  "$MODELS_DIR/Qwen3.8-27B-UD-Q4_K_S.gguf" \
  "/home/shawry/Qwen3.8-27B-UD-Q4_K_S.gguf" \
  "$MODELS_DIR/qwen-3.8-27b-coder-q4_k_s.gguf" \
  || true)"

QWEN38_DRAFT="$(find_first_existing \
  "$MODELS_DIR/mtp-Qwen3.8-27B-Q4_0.gguf" \
  "/home/shawry/mtp-Qwen3.8-27B-Q4_0.gguf" \
  || true)"

QWEN35_Q6_MODEL="$(find_first_existing \
  "/home/shawry/Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf" \
  "$MODELS_DIR/Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf" \
  "/home/shawry/Qwen3.6-35B-A3B-UD-Q6_K_L.gguf" \
  || true)"

QWEN35_Q4_MODEL="$(find_first_existing \
  "$HF_CACHE_DIR/models--unsloth--Qwen3.6-35B-A3B-GGUF/snapshots/a483e9e6cbd595906af30beda3187c2663a1118c/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf" \
  "$MODELS_DIR/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf" \
  "/home/shawry/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf" \
  || true)"

QWEN9B_MODEL="$(find_first_existing \
  "/home/shawry/Qwen3.5-9B-Q8_0.gguf" \
  "$MODELS_DIR/Qwen3.5-9B-Q8_0.gguf" \
  || true)"

# ── Model Profiles Configuration ──────────────────────────────────────────────
declare -A MODEL_NAME=(
  [1]="Qwen 3.8 27B UD-Q3_K_XL"
  [2]="Qwen 3.6 35B A3B UD-Q6_K_XL"
  [3]="Qwen 3.6 35B A3B UD-Q4_K_M"
  [4]="Qwen 3.5 9B Q8_0"
  [5]="Custom GGUF Model"
)

declare -A MODEL_FILE=(
  [1]="$QWEN38_MODEL"
  [2]="$QWEN35_Q6_MODEL"
  [3]="$QWEN35_Q4_MODEL"
  [4]="$QWEN9B_MODEL"
  [5]=""
)

declare -A MODEL_DESC=(
  [1]="12.2 GB · 100% GPU VRAM (ngl 99) · 2 Slots · 32K Context · Ultra Fast (~50-75 t/s)"
  [2]="31.0 GB · Hybrid GPU/CPU (ngl 15) · 2 Slots · 32K Context · High Precision (~15-25 t/s)"
  [3]="21.0 GB · Hybrid GPU/CPU (ngl 22) · 2 Slots · 32K Context · Balanced (~25-35 t/s)"
  [4]="8.9 GB · 100% GPU VRAM (ngl 99) · 4 Slots · 65K Context · Ultra Fast (~80-120 t/s)"
  [5]="User-specified model path & custom parameters"
)

declare -A MODEL_DEFAULT_PARALLEL=(
  [1]=2
  [2]=2
  [3]=2
  [4]=4
  [5]=2
)

declare -A MODEL_DEFAULT_CTX=(
  [1]=32768
  [2]=32768
  [3]=32768
  [4]=65536
  [5]=32768
)

declare -A MODEL_DEFAULT_NGL=(
  [1]=99
  [2]=15
  [3]=22
  [4]=99
  [5]=99
)

# ── CLI Selection or Interactive Menu ─────────────────────────────────────────
CHOICE="${1:-}"

if [[ -n "$CHOICE" && "$CHOICE" =~ ^[1-5]$ ]]; then
  shift
elif [[ -n "$CHOICE" && "$CHOICE" =~ ^- ]]; then
  CHOICE="2"
elif [[ -z "$CHOICE" ]]; then
  echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════════════════════╗${RESET}"
  echo -e "${CYAN}║${RESET}  ${BOLD}Qwen / Local LLM Server Launcher${RESET} · ${GREEN}RTX 5070 Ti (16GB) + 32GB RAM${RESET}                   ${CYAN}║${RESET}"
  echo -e "${CYAN}║${RESET}  Multi-Slot Continuous Batching · Streaming KV Persistence · Port ${BOLD}${PORT}${RESET}              ${CYAN}║${RESET}"
  echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════════════════════════╣${RESET}"
  for i in 1 2 3 4 5; do
    if [[ -f "${MODEL_FILE[$i]}" ]]; then
      status_icon="${GREEN}✓ Ready   ${RESET}"
    elif [[ "$i" == "5" ]]; then
      status_icon="${BLUE}⚙ Custom  ${RESET}"
    else
      status_icon="${YELLOW}↓ Download${RESET}"
    fi

    badge="   "
    tag=""
    if [[ "$i" == "2" ]]; then
      badge="${YELLOW}[★]${RESET}"
      tag=" ${YELLOW}(Default)${RESET}"
    fi

    printf "${CYAN}║${RESET} %b %b ${BOLD}${GREEN}%d)${RESET} ${BOLD}%-30s${RESET}%-11b                           ${CYAN}║${RESET}\n" \
      "$badge" "$status_icon" "$i" "${MODEL_NAME[$i]}" "$tag"
    printf "${CYAN}║${RESET}       ${DIM}↳ %-80s${RESET} ${CYAN}║${RESET}\n" "${MODEL_DESC[$i]}"
    if [[ "$i" -lt 5 ]]; then
      echo -e "${CYAN}╟──────────────────────────────────────────────────────────────────────────────────────────╢${RESET}"
    fi
  done
  echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════════════════════╝${RESET}"
  echo ""
  read -rp "Select model [1-5] (default: 2): " USER_INPUT
  CHOICE="${USER_INPUT:-2}"
fi

if ! [[ "$CHOICE" =~ ^[1-5]$ ]]; then
  echo -e "${RED}❌ Invalid selection: '${CHOICE}'. Please choose 1, 2, 3, 4, or 5.${RESET}"
  exit 1
fi

# ── Handle Custom Model (Option 5) ────────────────────────────────────────────
if [[ "$CHOICE" == "5" ]]; then
  CUSTOM_PATH="${1:-}"
  if [[ -n "$CUSTOM_PATH" && ! "$CUSTOM_PATH" =~ ^- ]]; then
    MODEL_PATH="$CUSTOM_PATH"
    shift
  else
    read -rp "Enter full path to GGUF model: " MODEL_PATH
  fi

  if [[ ! -f "$MODEL_PATH" ]]; then
    echo -e "${RED}❌ Model file not found at: ${MODEL_PATH}${RESET}"
    exit 1
  fi
  TARGET_MODEL="$MODEL_PATH"
  TARGET_NAME="Custom Model ($(basename "$MODEL_PATH"))"
else
  TARGET_MODEL="${MODEL_FILE[$CHOICE]}"
  TARGET_NAME="${MODEL_NAME[$CHOICE]}"
fi

# ── Active Parameters Resolution ──────────────────────────────────────────────
ACTIVE_PARALLEL="${PARALLEL:-${MODEL_DEFAULT_PARALLEL[$CHOICE]}}"
ACTIVE_CTX="${CTX_SIZE:-${MODEL_DEFAULT_CTX[$CHOICE]}}"
ACTIVE_NGL="${NGL:-${MODEL_DEFAULT_NGL[$CHOICE]}}"
ACTIVE_CTK="${CTK:-q8_0}"
ACTIVE_CTV="${CTV:-q8_0}"
SLOT_CTX=$(( ACTIVE_CTX / ACTIVE_PARALLEL ))

# ── Speculative Decoding Configuration ────────────────────────────────────────
SPEC_FLAGS=()
if [[ -n "${SPEC_EXTRA:-}" ]]; then
  read -r -a SPEC_FLAGS <<< "$SPEC_EXTRA"
fi

# ── Pre-flight Checks ─────────────────────────────────────────────────────────

# 1. Ensure KV Cache directory exists
mkdir -p "$KV_CACHE_DIR"

# 2. Port conflict / active server check
if curl -s "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo -e "${YELLOW}⚠️  A server instance is already running and healthy on port ${PORT}.${RESET}"
  echo -e "   Check: ${BOLD}curl -s http://127.0.0.1:${PORT}/slots | jq .${RESET}"
  exit 0
fi

# 3. Prevent duplicate concurrent startup
LOCK_FILE="/tmp/qwen-${PORT}.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo -e "${YELLOW}⏳ Another server instance is currently loading on port ${PORT}. Please wait...${RESET}"
  exit 0
fi

# 4. Check CUDA GPU availability
if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L 2>/dev/null | grep -qi "GPU"; then
  echo -e "${RED}❌ ERROR: No NVIDIA CUDA GPU detected via nvidia-smi.${RESET}"
  echo -e "   Running large quantized models in CPU-only mode will exhaust system RAM."
  echo -e "   Please verify NVIDIA drivers and GPU availability."
  exit 1
fi

# 5. Check model file existence / Trigger automated download if Option 1
if [[ ! -f "$TARGET_MODEL" ]]; then
  if [[ "$CHOICE" == "1" ]]; then
    echo -e "${YELLOW}📥 Qwen 3.8 27B model not found at:${RESET} ${TARGET_MODEL}"
    DOWNLOAD_SCRIPT="/home/shawry/Documents/GitHub/SwarmAIStudio/scripts/download_qwen38_27b.py"
    if [[ -f "$DOWNLOAD_SCRIPT" ]]; then
      echo -e "${CYAN}🚀 Starting automated high-speed resumable downloader...${RESET}"
      python3 "$DOWNLOAD_SCRIPT" || {
        echo -e "${RED}❌ Download interrupted. You can run Option 2 in the meantime.${RESET}"
        exit 1
      }
    else
      echo -e "${RED}❌ Model file not found and download script missing.${RESET}"
      exit 1
    fi
  else
    echo -e "${RED}❌ Model file not found at:${RESET} ${TARGET_MODEL}"
    exit 1
  fi
fi

# 6. Protect desktop environment from OOM killer
# Set oom_score_adj to 700 so kernel sacrifices this server first before desktop/IDE
echo 700 > /proc/self/oom_score_adj 2>/dev/null || true

# ── Summary Display ───────────────────────────────────────────────────────────
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════════╗${RESET}"
printf "${CYAN}║${RESET} ${BOLD}%-76s${RESET} ${CYAN}║${RESET}\n" "🚀 Starting: ${TARGET_NAME}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════════════╣${RESET}"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Model Path:" "$(basename "$TARGET_MODEL")"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Server Binary:" "$(basename "$SERVER_BIN")"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Endpoint:" "http://${HOST}:${PORT}"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Slots / Capacity:" "${ACTIVE_PARALLEL} slots (~${SLOT_CTX} tokens/slot)"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Total Context:" "${ACTIVE_CTX} tokens"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "GPU Layers (ngl):" "${ACTIVE_NGL}"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "KV Cache Format:" "K=${ACTIVE_CTK}, V=${ACTIVE_CTV} (Quantized)"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Flash Attention:" "Enabled (-fa on)"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Continuous Batch:" "Enabled (-cb)"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Prefix Cache Reuse:" "Chunk threshold ${CACHE_REUSE}"
printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Slot KV Storage:" "${KV_CACHE_DIR}"
if [[ ${#SPEC_FLAGS[@]} -gt 0 ]]; then
  printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Speculative Decode:" "${SPEC_FLAGS[*]}"
else
  printf "${CYAN}║${RESET}  %-22s %-52s ${CYAN}║${RESET}\n" "Speculative Decode:" "None"
fi
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════════╝${RESET}"

# ── Launch llama-server ───────────────────────────────────────────────────────
# Unified execution command with consistent multi-slot, KV persistence, and metrics flags
exec "$SERVER_BIN" \
  -m "$TARGET_MODEL" \
  -ngl "$ACTIVE_NGL" \
  -c "$ACTIVE_CTX" \
  -np "$ACTIVE_PARALLEL" \
  -cb \
  -fa on \
  -ctk "$ACTIVE_CTK" \
  -ctv "$ACTIVE_CTV" \
  --slot-save-path "$KV_CACHE_DIR" \
  --cache-reuse "$CACHE_REUSE" \
  --slots \
  --metrics \
  -b "$BATCH_SIZE" \
  -ub "$UBATCH_SIZE" \
  --temp "$TEMP" \
  --top-p "$TOP_P" \
  --top-k "$TOP_K" \
  --min-p "$MIN_P" \
  --presence-penalty "$PRESENCE_PENALTY" \
  --repeat-penalty "$REPEAT_PENALTY" \
  --reasoning-budget "$REASONING_BUDGET" \
  --host "$HOST" \
  --port "$PORT" \
  "${SPEC_FLAGS[@]}" \
  "$@"
