"""
Hardware Telemetry & Metrics Engine (NVIDIA GPU VRAM/Util, CPU & RAM)
"""

import subprocess
import psutil
from typing import Dict, Any

def get_hardware_metrics() -> Dict[str, Any]:
    gpu_data = {
        "name": "RTX 5070 Ti",
        "util": 0.0,
        "mem_used": 0.0,
        "mem_total": 16303.0,
        "mem_percent": 0.0,
        "temp": 0.0,
        "power": 0.0
    }
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits"
        ]
        out = subprocess.check_output(cmd, text=True, timeout=0.8).strip().split(",")
        if len(out) >= 6:
            gpu_data["name"] = out[0].replace("NVIDIA GeForce ", "").strip()
            gpu_data["util"] = float(out[1].strip())
            used_mb = float(out[2].strip())
            total_mb = float(out[3].strip())
            gpu_data["mem_used"] = used_mb
            gpu_data["mem_total"] = total_mb
            gpu_data["mem_percent"] = round((used_mb / total_mb) * 100, 1) if total_mb > 0 else 0
            gpu_data["temp"] = float(out[4].strip())
            gpu_data["power"] = float(out[5].strip())
    except Exception:
        pass

    ram = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=None)

    return {
        "gpu": gpu_data,
        "cpu_percent": cpu_pct,
        "ram_used_gb": round(ram.used / (1024**3), 1),
        "ram_total_gb": round(ram.total / (1024**3), 1),
        "ram_percent": ram.percent
    }
