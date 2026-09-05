"""
Web Scout & Live External Grounding Engine for Swarm AI Studio
Performs live web queries and Context7 documentation retrieval
to ground questions with verified external facts.
"""

import subprocess
import urllib.request
import urllib.parse
import json
import re
import time
from typing import Dict, List, Any
from swarm.logger import log_event
from swarm.context7_engine import fetch_latest_doc_context

def search_web_live(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """
    Performs a live web search using lightweight retrieval.
    Returns list of dicts with title, snippet, and link.
    """
    t0 = time.time()
    results: List[Dict[str, str]] = []
    
    # 1. DuckDuckGo HTML / Instant Answer lookup
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Parse snippets
            raw_results = re.findall(r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
            for link, snippet in raw_results[:max_results]:
                clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                clean_snippet = clean_snippet.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'")
                clean_link = link.strip()
                if "uddg=" in clean_link:
                    try:
                        clean_link = urllib.parse.unquote(clean_link.split("uddg=")[1].split("&")[0])
                    except Exception:
                        pass
                if clean_snippet:
                    results.append({
                        "title": clean_snippet[:80] + "...",
                        "snippet": clean_snippet,
                        "url": clean_link
                    })
    except Exception as e:
        log_event("warn", "web_scout", f"DuckDuckGo search error: {e}")

    # Fallback to Context7 if search yielded few results and query looks technical
    if len(results) < 2:
        words = [w for w in query.split() if len(w) > 2 and w.isalnum()]
        if words:
            c7_context = fetch_latest_doc_context(words[0], query)
            if c7_context and "[Context7] No live" not in c7_context:
                results.append({
                    "title": f"Context7 Live Docs: {words[0]}",
                    "snippet": c7_context[:600],
                    "url": "https://context7.ai"
                })

    dur = round((time.time() - t0) * 1000, 1)
    log_event("info", "web_scout", f"Web scout found {len(results)} sources for '{query[:40]}' ({dur}ms)")
    return results

def format_web_scout_prompt_block(query: str, results: List[Dict[str, str]]) -> str:
    """Formats live web search results into a clean prompt grounding block."""
    if not results:
        return f"=== LIVE WEB GROUNDING ===\nQuery: {query}\nStatus: No external web citations needed or retrieved.\n=========================="

    lines = [f"=== LIVE WEB & DOCUMENTATION GROUNDING ({len(results)} verified sources) ===", f"Target Query: {query}"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[Source {i}]: {r['title']}")
        lines.append(f"Snippet: {r['snippet']}")
        if r.get('url'):
            lines.append(f"URL: {r['url']}")
    lines.append("==========================================================================")
    return "\n".join(lines)
