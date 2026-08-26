"""
Artifact File Vault & Remote LAN Document Reader (Grouped by Repository)
"""

import time
import re
from pathlib import Path
from urllib.parse import quote_plus
from typing import List, Dict, Any
from swarm.config import ARTIFACTS_DIR
from swarm.logger import log_event

def save_artifact_to_disk(title: str, filename: str, content: str, repo_path: str = "") -> Dict[str, str]:
    safe_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    
    repo_name = "Global"
    repo_file_path = ""
    if repo_path:
        rp = Path(repo_path)
        if rp.exists() and rp.is_dir():
            repo_name = rp.name
            try:
                repo_target = rp / safe_filename
                repo_target.write_text(content, encoding="utf-8")
                repo_file_path = str(repo_target)
            except Exception:
                pass

    # Save under repo-specific subfolder in centralized artifacts dir
    repo_vault_dir = ARTIFACTS_DIR / repo_name
    repo_vault_dir.mkdir(parents=True, exist_ok=True)
    
    central_path = repo_vault_dir / safe_filename
    central_path.write_text(content, encoding="utf-8")
    
    log_event("info", "artifact", f"Saved artifact '{safe_filename}' under repo '{repo_name}'", {"path": str(central_path)})

    return {
        "title": title,
        "filename": safe_filename,
        "repo_name": repo_name,
        "path": str(central_path),
        "repo_path": repo_file_path,
        "read_url": f"/api/artifacts/read?path={quote_plus(str(central_path))}",
        "content": content
    }

def scan_all_artifacts(repo_path: str = "") -> Dict[str, Any]:
    """Scans and groups all generated artifacts and repo docs by repository."""
    groups_dict = {}
    seen = set()

    # 1. Scan Central Artifacts Directory (~/.swarm/artifacts/)
    if ARTIFACTS_DIR.exists():
        for item in ARTIFACTS_DIR.rglob("*"):
            if item.is_file() and item.suffix in [".md", ".txt", ".json", ".cs", ".py", ".ts", ".html"]:
                try:
                    rel_parts = item.relative_to(ARTIFACTS_DIR).parts
                    group_name = rel_parts[0] if len(rel_parts) > 1 else "Global Artifacts"
                    
                    stat = item.stat()
                    art_obj = {
                        "name": item.name,
                        "repo_name": group_name,
                        "path": str(item),
                        "size": stat.st_size,
                        "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                        "type": "Swarm Report",
                        "read_url": f"/api/artifacts/read?path={quote_plus(str(item))}"
                    }
                    if group_name not in groups_dict:
                        groups_dict[group_name] = []
                    groups_dict[group_name].append(art_obj)
                    seen.add(str(item))
                except Exception:
                    pass

    # 2. Scan active Repository Docs if provided
    if repo_path:
        rp = Path(repo_path)
        if rp.exists() and rp.is_dir():
            repo_title = rp.name
            if repo_title not in groups_dict:
                groups_dict[repo_title] = []

            for f in rp.iterdir():
                if f.is_file() and f.suffix == ".md" and str(f) not in seen:
                    try:
                        stat = f.stat()
                        art_obj = {
                            "name": f.name,
                            "repo_name": repo_title,
                            "path": str(f),
                            "size": stat.st_size,
                            "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                            "type": "Repository Doc",
                            "read_url": f"/api/artifacts/read?path={quote_plus(str(f))}"
                        }
                        groups_dict[repo_title].append(art_obj)
                        seen.add(str(f))
                    except Exception:
                        pass

    selected_repo_name = Path(repo_path).name if repo_path else ""

    # Format into sorted group list (selected repo placed first)
    groups_list = []
    for r_name, items in groups_dict.items():
        items.sort(key=lambda x: x["modified"], reverse=True)
        is_sel = (r_name.lower() == selected_repo_name.lower()) if selected_repo_name else False
        groups_list.append({
            "repo_name": r_name,
            "is_selected": is_sel,
            "count": len(items),
            "artifacts": items
        })

    # Sort so selected repo is first, followed alphabetically
    groups_list.sort(key=lambda g: (not g["is_selected"], g["repo_name"]))
    
    # Flattened list for backward compatibility
    flat_list = []
    for g in groups_list:
        flat_list.extend(g["artifacts"])

    return {
        "selected_repo": selected_repo_name,
        "groups": groups_list,
        "flat": flat_list,
        "total_count": len(flat_list)
    }
