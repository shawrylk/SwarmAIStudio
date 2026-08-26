"""
Artifact File Vault & Remote LAN Document Reader
"""

import time
import re
from pathlib import Path
from urllib.parse import quote_plus
from typing import List, Dict, Any
from swarm.config import ARTIFACTS_DIR

def save_artifact_to_disk(title: str, filename: str, content: str, repo_path: str = "") -> Dict[str, str]:
    safe_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    central_path = ARTIFACTS_DIR / safe_filename
    central_path.write_text(content, encoding="utf-8")
    
    repo_file_path = ""
    if repo_path:
        rp = Path(repo_path)
        if rp.exists() and rp.is_dir():
            try:
                repo_target = rp / safe_filename
                repo_target.write_text(content, encoding="utf-8")
                repo_file_path = str(repo_target)
            except Exception:
                pass

    return {
        "title": title,
        "filename": safe_filename,
        "path": str(central_path),
        "repo_path": repo_file_path,
        "read_url": f"/api/artifacts/read?path={quote_plus(str(central_path))}",
        "content": content
    }

def scan_all_artifacts(repo_path: str = "") -> List[Dict[str, Any]]:
    artifacts = []
    seen = set()

    if ARTIFACTS_DIR.exists():
        for f in ARTIFACTS_DIR.iterdir():
            if f.is_file() and f.suffix in [".md", ".txt", ".json", ".cs", ".py", ".ts", ".html"]:
                try:
                    stat = f.stat()
                    artifacts.append({
                        "name": f.name,
                        "path": str(f),
                        "size": stat.st_size,
                        "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                        "type": "Swarm Artifact",
                        "read_url": f"/api/artifacts/read?path={quote_plus(str(f))}"
                    })
                    seen.add(str(f))
                except Exception:
                    pass

    if repo_path:
        rp = Path(repo_path)
        if rp.exists() and rp.is_dir():
            for f in rp.iterdir():
                if f.is_file() and f.suffix == ".md" and str(f) not in seen:
                    try:
                        stat = f.stat()
                        artifacts.append({
                            "name": f"{rp.name}/{f.name}",
                            "path": str(f),
                            "size": stat.st_size,
                            "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                            "type": "Repository Doc",
                            "read_url": f"/api/artifacts/read?path={quote_plus(str(f))}"
                        })
                        seen.add(str(f))
                    except Exception:
                        pass

    artifacts.sort(key=lambda x: x["modified"], reverse=True)
    return artifacts
