"""
AI Factory Pipeline v5.8.12 — Mother Memory Retrieval Helpers
Issue 21: Stage AI calls pull specific context slices instead of
          receiving the entire state stuffed into one prompt.
"""
from __future__ import annotations
import logging
from typing import Optional
from factory.memory.mother_memory import (
    _fallback_insights, get_recent_insights,
)
logger = logging.getLogger("factory.memory.retrieval")

def _filter_insights(
    insights: list[dict], insight_type: str, project_id: str
) -> list[dict]:
    return [
        r for r in insights
        if r.get("insight_type") == insight_type
        and (not project_id or r.get("project_id", "") == project_id)
    ]

def _parse_kv(content: str, prefix: str) -> dict:
    """Parse 'PREFIX:k1|k2|...' into a rough dict for display."""
    body = content[len(prefix):] if content.startswith(prefix) else content
    parts = body.split("|")
    return {"_raw": body, "_parts": parts}


async def get_requirements(
    project_id: str, filter_priority: Optional[str] = None
) -> list[dict]:
    records = _filter_insights(list(_fallback_insights), "requirement", project_id)
    out = []
    for r in records:
        d = _parse_kv(r.get("content", ""), "REQ:")
        if filter_priority and filter_priority not in d.get("_raw", ""):
            continue
        out.append({"id": r.get("id",""), "content": r.get("content",""), **d})
    return out


async def get_screens(project_id: str) -> list[dict]:
    records = _filter_insights(list(_fallback_insights), "screen", project_id)
    return [
        {"id": r.get("id",""), "content": r.get("content",""),
         **_parse_kv(r.get("content",""), "SCREEN:")}
        for r in records
    ]


async def get_api_spec(project_id: str) -> list[dict]:
    records = _filter_insights(list(_fallback_insights), "api_endpoint", project_id)
    return [
        {"id": r.get("id",""), "content": r.get("content",""),
         **_parse_kv(r.get("content",""), "API:")}
        for r in records
    ]


async def get_data_models(project_id: str) -> list[dict]:
    records = _filter_insights(list(_fallback_insights), "data_model", project_id)
    return [
        {"id": r.get("id",""), "content": r.get("content",""),
         **_parse_kv(r.get("content",""), "MODEL:")}
        for r in records
    ]


async def get_legal_clauses_for(
    project_id: str, doc_type: Optional[str] = None
) -> list[dict]:
    records = _filter_insights(list(_fallback_insights), "legal_clause", project_id)
    out = []
    for r in records:
        d = _parse_kv(r.get("content",""), "LEGAL:")
        if doc_type and doc_type not in d.get("_raw",""):
            continue
        out.append({"id": r.get("id",""), "content": r.get("content",""), **d})
    return out


async def get_related_files(
    project_id: str,
    screen_name: Optional[str] = None,
) -> list[dict]:
    records = _filter_insights(list(_fallback_insights), "source_file", project_id)
    out = []
    for r in records:
        d = _parse_kv(r.get("content",""), "FILE:")
        if screen_name and screen_name.lower() not in d.get("_raw","").lower():
            continue
        out.append({"id": r.get("id",""), "content": r.get("content",""), **d})
    return out


async def similar_patterns_across_projects(
    pattern_desc: str, limit: int = 5
) -> list[dict]:
    """Keyword-based cross-project pattern search (no embeddings required)."""
    keywords = [w.lower() for w in pattern_desc.split() if len(w) > 3]
    if not keywords:
        return []
    results = []
    for r in reversed(list(_fallback_insights)):
        content_lower = r.get("content","").lower()
        if sum(1 for kw in keywords if kw in content_lower) >= max(1, len(keywords)//2):
            results.append({"content": r.get("content",""), "project_id": r.get("project_id","")})
        if len(results) >= limit:
            break
    return results


async def check_consistency(project_id: str) -> list[str]:
    """
    Issue 21 §7: Before closing a stage, check that every blueprint screen
    has a design asset, and every requirement has a source file.
    Returns a list of inconsistency strings (empty = consistent).
    """
    screens = await get_screens(project_id)
    files = await get_related_files(project_id)
    file_names = {
        r.get("content","").split("|")[0].replace("FILE:","").split("/")[-1].lower()
        for r in files
    }
    issues: list[str] = []
    for screen in screens:
        raw = screen.get("_raw","")
        # Extract screen name from content: SCREEN:{id}|{name}|...
        parts = raw.split("|")
        screen_name = parts[1].lower() if len(parts) > 1 else ""
        if screen_name and not any(screen_name.replace(" ","_") in fn or screen_name.replace(" ","") in fn for fn in file_names):
            issues.append(f"Screen '{screen_name}' has no matching source file")
    return issues
