"""
Dynamic Model Scouting & Assignment Engine
Scouts Gemini CLI models & Qwen 3.8 frontier series on startup and dynamically.
"""

import time
import json
import re
import subprocess
from typing import List, Dict, Any
from swarm.config import MODELS_CONFIG_FILE

SCOUTED_MODELS_CACHE = {
    "last_scouted": 0,
    "catalog": {
        "gemini": [],
        "qwen": []
    }
}

def scout_gemini_models() -> List[Dict[str, str]]:
    models = []
    try:
        out = subprocess.check_output(["agy", "models"], text=True, timeout=8)
        for line in out.strip().split("\n"):
            cleaned = re.sub(r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏\s]+", "", line).strip()
            if not cleaned or "Fetching" in cleaned:
                continue
            if "\t" in cleaned:
                parts = cleaned.split("\t", 1)
                m_id = parts[0].strip()
                m_name = parts[1].strip()
            else:
                parts = re.split(r"\s{2,}", cleaned, maxsplit=1)
                m_id = parts[0].strip()
                m_name = parts[1].strip() if len(parts) > 1 else m_id
            
            tier = "Pro / High Reasoning" if any(k in m_id for k in ["high", "pro", "opus"]) else "Fast / Flash"
            models.append({
                "id": m_id,
                "name": m_name,
                "provider": "gemini",
                "tier": tier
            })
    except Exception:
        models = [
            {"id": "gemini-3.7-flash-high", "name": "Gemini 3.7 Flash (High)", "provider": "gemini", "tier": "Fast"},
            {"id": "gemini-3.1-pro-high", "name": "Gemini 3.1 Pro (High)", "provider": "gemini", "tier": "Pro"},
            {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6 (Thinking)", "provider": "gemini", "tier": "Pro"}
        ]
    return models

def scout_qwen_models() -> List[Dict[str, str]]:
    return [
        {"id": "qwen-3.8-max", "name": "Qwen 3.8 Max (Flagship 2.4T MoE)", "provider": "qwen", "tier": "Frontier Max"},
        {"id": "qwen-3.8-coder", "name": "Qwen 3.8 Coder (1M Context)", "provider": "qwen", "tier": "Agentic Coding"},
        {"id": "qwen-3.8-thinking", "name": "Qwen 3.8 Thinking Mode", "provider": "qwen", "tier": "Deep Reasoning"},
        {"id": "qwen-3.8-27b", "name": "Qwen 3.8 27B Dense", "provider": "qwen", "tier": "Dense"},
        {"id": "qwen-3.5-max", "name": "Qwen 3.5 Max", "provider": "qwen", "tier": "Cloud Max"},
        {"id": "qwen-3.5-plus", "name": "Qwen 3.5 Plus", "provider": "qwen", "tier": "Cloud Plus"},
        {"id": "qwen-3.0", "name": "Qwen 3.0 Thinking", "provider": "qwen", "tier": "Thinking"},
        {"id": "qwen-2.5-max", "name": "Qwen 2.5 Max", "provider": "qwen", "tier": "Legacy Max"}
    ]

def scout_lfm_models() -> List[Dict[str, str]]:
    return [
        {"id": "Qwen3.8-27B-UD-Q3_K_XL.gguf", "name": "Qwen 3.8 27B UD-Q3_K_XL (MTP Drafter · Full GPU)", "provider": "local_gpu", "tier": "Local GPU (4 Slots · Fast)"},
        {"id": "Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf", "name": "Qwen 3.6 35B A3B UD-Q6_K_XL (High Precision MoE)", "provider": "local_gpu", "tier": "Local GPU (2 Slots · High Precision)"},
        {"id": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf", "name": "Qwen 3.6 35B A3B UD-Q4_K_M (Balanced MoE)", "provider": "local_gpu", "tier": "Local GPU (2 Slots · Balanced)"},
        {"id": "Qwen3.5-9B-Q8_0.gguf", "name": "Qwen 3.5 9B Q8_0 (131K Context · Ultra Fast)", "provider": "local_gpu", "tier": "Local GPU (4 Slots · Ultra Fast)"},
        {"id": "qwen-3.8-27b-coder-q4_k_s.gguf", "name": "Qwen 3.8 27B Coder (Legacy Alias)", "provider": "local_gpu", "tier": "Local GPU (Legacy)"},
        {"id": "LFM2.5-VL-3B-Q8_0.gguf", "name": "Liquid LFM 2.5 VL (3B Q8 Vision)", "provider": "liquid_lfm", "tier": "Fast Satellite (150 t/s)"},
        {"id": "lfm2.5-vl-3b", "name": "Liquid LFM 2.5 VL 3B (Alias)", "provider": "liquid_lfm", "tier": "Fast Satellite"},
        {"id": "LFM2.5-2.6B-Q8_0.gguf", "name": "Liquid LFM 2.5 (2.6B Q8 Dense)", "provider": "liquid_lfm", "tier": "Fast Satellite"}
    ]

def scout_all_models(force_refresh: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force_refresh and (now - SCOUTED_MODELS_CACHE["last_scouted"] < 60) and SCOUTED_MODELS_CACHE["catalog"]["gemini"]:
        return SCOUTED_MODELS_CACHE["catalog"]

    catalog = {
        "gemini": scout_gemini_models(),
        "qwen": scout_qwen_models(),
        "lfm": scout_lfm_models()
    }
    SCOUTED_MODELS_CACHE["catalog"] = catalog
    SCOUTED_MODELS_CACHE["last_scouted"] = now
    return catalog

def load_model_assignments() -> Dict[str, str]:
    if MODELS_CONFIG_FILE.exists():
        try:
            return json.loads(MODELS_CONFIG_FILE.read_text())
        except Exception:
            pass
    return {
        "gemini": "gemini-3.1-pro-high",
        "qwen": "qwen-3.8-max",
        "lfm": "Qwen3.8-27B-UD-Q3_K_XL.gguf"
    }

def save_model_assignments(assignments: Dict[str, str]):
    try:
        MODELS_CONFIG_FILE.write_text(json.dumps(assignments, indent=2))
    except Exception:
        pass

