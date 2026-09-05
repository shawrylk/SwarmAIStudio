#!/usr/bin/env python3
"""
High-Speed Resumable Multi-Threaded Downloader for Qwen 3.8 27B & MTP Drafter
Downloads official Unsloth dynamic quant models directly with chunk-level resume,
multi-threaded range fetching, and live progress logging.
"""

import sys
import os
import time
import math
import json
import argparse
import urllib.request
import concurrent.futures
from pathlib import Path

MODELS_DIR = Path.home() / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = MODELS_DIR / "download.log"

HF_REPO = "unsloth/Qwen3.8-27B-GGUF"
FILES_CONFIG = {
    "main": {
        "filename": "Qwen3.8-27B-UD-Q3_K_XL.gguf",
        "url_path": "Qwen3.8-27B-UD-Q3_K_XL.gguf",
        "dest": MODELS_DIR / "Qwen3.8-27B-UD-Q3_K_XL.gguf",
    },
    "mtp": {
        "filename": "mtp-Qwen3.8-27B-Q4_0.gguf",
        "url_path": "MTP/mtp-Qwen3.8-27B-Q4_0.gguf",
        "dest": MODELS_DIR / "mtp-Qwen3.8-27B-Q4_0.gguf",
    }
}

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB chunks
MAX_WORKERS = 12               # 12 parallel connections

def log_msg(msg: str, also_stdout: bool = True):
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{timestamp} {msg}"
    if also_stdout:
        print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def get_direct_url_and_size(hf_path: str) -> tuple[str, int]:
    base_url = f"https://huggingface.co/{HF_REPO}/resolve/main/{hf_path}"
    req = urllib.request.Request(base_url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        direct_url = resp.geturl()
        size = int(resp.headers.get("Content-Length", 0))
    return direct_url, size

def download_chunk(url: str, start: int, end: int, part_file: Path, max_retries: int = 5) -> int:
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
                "Range": f"bytes={start}-{end}"
            })
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = resp.read()
                expected = end - start + 1
                if len(data) != expected:
                    raise IOError(f"Short read: expected {expected} bytes, received {len(data)}")
                with open(part_file, "r+b" if part_file.exists() else "wb") as f:
                    f.seek(start)
                    f.write(data)
                return len(data)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1.0 * (attempt + 1))
    return 0

def download_file(file_key: str, force: bool = False) -> Path:
    info = FILES_CONFIG[file_key]
    dest = info["dest"]
    url_path = info["url_path"]
    filename = info["filename"]

    if dest.exists() and not force:
        size_gb = dest.stat().st_size / (1024**3)
        log_msg(f"✅ {filename} already exists at {dest} ({size_gb:.2f} GB). Skipping download.")
        return dest

    log_msg(f"🚀 Resolving download stream for {filename} from {HF_REPO}...")
    direct_url, total_size = get_direct_url_and_size(url_path)
    total_gb = total_size / (1024**3)
    log_msg(f"📦 Total size: {total_gb:.2f} GB ({total_size:,} bytes)")

    part_file = dest.with_suffix(dest.suffix + ".part")
    state_file = dest.with_suffix(dest.suffix + ".state.json")

    # Load resume state if available
    completed_chunks = set()
    if state_file.exists() and part_file.exists():
        try:
            with open(state_file, "r") as f:
                state = json.load(f)
                if state.get("total_size") == total_size:
                    completed_chunks = set(state.get("completed", []))
                    log_msg(f"🔁 Resuming download: {len(completed_chunks)} chunks already verified.")
        except Exception:
            completed_chunks = set()

    if not part_file.exists():
        with open(part_file, "wb") as f:
            f.seek(total_size - 1)
            f.write(b"\0")

    num_chunks = math.ceil(total_size / CHUNK_SIZE)
    pending_chunks = []
    for i in range(num_chunks):
        if i not in completed_chunks:
            start = i * CHUNK_SIZE
            end = min((i + 1) * CHUNK_SIZE - 1, total_size - 1)
            pending_chunks.append((i, start, end))

    downloaded_bytes = len(completed_chunks) * CHUNK_SIZE
    # Adjust for potential last chunk size difference
    if (num_chunks - 1) in completed_chunks:
        last_chunk_actual = total_size - (num_chunks - 1) * CHUNK_SIZE
        downloaded_bytes = downloaded_bytes - CHUNK_SIZE + last_chunk_actual

    log_msg(f"📥 Downloading {len(pending_chunks)}/{num_chunks} chunks with {MAX_WORKERS} parallel threads...")
    start_time = time.time()
    session_downloaded = 0
    last_log_time = start_time
    last_save_state_time = start_time

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(download_chunk, direct_url, start, end, part_file): (i, start, end)
            for (i, start, end) in pending_chunks
        }

        for future in concurrent.futures.as_completed(future_map):
            idx, start, end = future_map[future]
            try:
                n_bytes = future.result()
                completed_chunks.add(idx)
                session_downloaded += n_bytes
                downloaded_bytes += n_bytes
            except Exception as e:
                log_msg(f"❌ Error downloading chunk {idx}: {e}")
                raise

            now = time.time()
            if now - last_save_state_time >= 5.0:
                try:
                    with open(state_file, "w") as f:
                        json.dump({"total_size": total_size, "completed": list(completed_chunks)}, f)
                    last_save_state_time = now
                except Exception:
                    pass

            if now - last_log_time >= 4.0 or downloaded_bytes >= total_size:
                elapsed = now - start_time
                speed_mb = (session_downloaded / (1024**2)) / max(elapsed, 0.001)
                percent = (downloaded_bytes / total_size) * 100
                remaining_bytes = total_size - downloaded_bytes
                eta_s = remaining_bytes / max(speed_mb * 1024 * 1024, 1)
                eta_m = int(eta_s // 60)
                eta_rem_s = int(eta_s % 60)
                log_msg(
                    f"⏳ [{filename}] {percent:5.1f}% | "
                    f"{downloaded_bytes/(1024**3):.2f}/{total_gb:.2f} GB | "
                    f"{speed_mb:6.1f} MB/s | ETA: {eta_m}m {eta_rem_s:02d}s"
                )
                last_log_time = now

    # Clean up state file and rename part file
    if state_file.exists():
        state_file.unlink()
    if dest.exists():
        dest.unlink()
    part_file.rename(dest)

    total_time = time.time() - start_time
    avg_speed = (session_downloaded / (1024**2)) / max(total_time, 0.001)
    log_msg(f"🎉 Successfully downloaded {filename} ({total_gb:.2f} GB) in {int(total_time//60)}m {int(total_time%60)}s (avg {avg_speed:.1f} MB/s)!")
    return dest

def main():
    parser = argparse.ArgumentParser(description="Download Qwen 3.8 27B and MTP models.")
    parser.add_argument("--target", choices=["all", "main", "mtp"], default="all", help="Target model to download")
    parser.add_argument("--force", action="store_true", help="Force re-download even if file exists")
    args = parser.parse_args()

    targets = ["main", "mtp"] if args.target == "all" else [args.target]
    for target in targets:
        download_file(target, force=args.force)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_msg("⚠️ Download interrupted by user.")
        sys.exit(130)
    except Exception as e:
        log_msg(f"❌ Fatal download error: {e}")
        sys.exit(1)


