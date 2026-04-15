"""
AI Factory Pipeline v5.8 — Stack Overflow Scout (Dev Q&A, No Key, ~300 req/day)

Queries the StackExchange API for high-quality developer questions and answers.
Anonymous access: ~300 requests/day per IP. No API key required (but adding
a registered app key raises the limit to 10,000/day — optional).

Best for: concrete technical solutions, library usage, error diagnosis,
API implementation patterns, version-specific answers.

The StackExchange API returns accepted/highest-voted answers inline,
giving us both the question context AND the solution in one call.

Spec Authority: v5.6 §2.2.3 (Scout provider interface)
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.stackoverflow_scout")

STACKOVERFLOW_COST_PER_CALL: float = 0.0
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))
# Optional: register at stackapps.com and set for 10K req/day
_APP_KEY: str = os.getenv("STACKEXCHANGE_APP_KEY", "")

_TIMEOUT = aiohttp.ClientTimeout(total=12)
_MAX_QUESTIONS = 3       # fetch top 3 questions
_MIN_SCORE = 3           # skip low-quality questions
_MIN_ANSWER_SCORE = 1    # skip unvoted answers

_BASE_URL = "https://api.stackexchange.com/2.3"
_HEADERS = {"Accept-Encoding": "gzip", "Accept": "application/json"}

# StackExchange sites by domain
_DOMAIN_SITES: dict[str, list[str]] = {
    "tech":      ["stackoverflow", "softwareengineering"],
    "legal":     ["law", "stackoverflow"],      # law.stackexchange for regulatory
    "market":    ["startups", "stackoverflow"],
    "community": ["softwareengineering", "stackoverflow"],
    "factual":   ["stackoverflow", "superuser"],
    "general":   ["stackoverflow"],
}


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

async def call_stackoverflow(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
    domain: str = "tech",
) -> tuple[str, float]:
    """Search StackExchange for high-voted Q&A relevant to the query.

    Fetches questions with accepted/highest answers inline.
    Filters by score to ensure quality.
    """
    query = prompt.strip()[:200]
    q_hash = _query_hash(query)

    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[stackoverflow] cache hit for '{query[:60]}'")
        return cached, STACKOVERFLOW_COST_PER_CALL

    sites = _DOMAIN_SITES.get(domain, ["stackoverflow"])
    all_results: list[dict] = []

    for site in sites[:2]:
        questions = await _search_questions(query, site)
        if questions:
            all_results.extend(questions)
            break  # one good site is enough; preserve quota

    if not all_results:
        return (
            f"[STACKOVERFLOW-NO-RESULTS] No Stack Overflow answers found for: {query[:100]}",
            STACKOVERFLOW_COST_PER_CALL,
        )

    # Fetch answers for top questions
    question_ids = [q["question_id"] for q in all_results[:_MAX_QUESTIONS]]
    answers = await _fetch_answers(question_ids, sites[0])

    formatted = _format_results(all_results[:_MAX_QUESTIONS], answers, query)
    await _store_cached(q_hash, "stackoverflow", query, formatted, state)
    logger.info(f"[stackoverflow] {len(all_results)} questions found for '{query[:60]}'")
    return formatted, STACKOVERFLOW_COST_PER_CALL


# ═══════════════════════════════════════════════════════════════════
# StackExchange API Calls
# ═══════════════════════════════════════════════════════════════════

async def _search_questions(query: str, site: str) -> list[dict]:
    """Search questions on a StackExchange site."""
    params: dict = {
        "intitle":   query,
        "site":      site,
        "sort":      "relevance",
        "order":     "desc",
        "filter":    "!9_bDE(fI5",   # includes body excerpt
        "pagesize":  10,
        "page":      1,
    }
    if _APP_KEY:
        params["key"] = _APP_KEY

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
            async with session.get(f"{_BASE_URL}/search", params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"[stackoverflow] HTTP {resp.status} on {site}")
                    return []
                data = await resp.json()

        items = data.get("items", [])
        filtered = [
            q for q in items
            if q.get("score", 0) >= _MIN_SCORE and q.get("is_answered", False)
        ]
        filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
        return filtered[:_MAX_QUESTIONS]

    except Exception as e:
        logger.debug(f"[stackoverflow] search error on {site}: {e}")
        return []


async def _fetch_answers(question_ids: list[int], site: str) -> dict[int, list[dict]]:
    """Fetch top answers for a list of question IDs."""
    if not question_ids:
        return {}

    ids_str = ";".join(str(qid) for qid in question_ids)
    params: dict = {
        "site":     site,
        "sort":     "votes",
        "order":    "desc",
        "filter":   "!9_bDE(fI5",
        "pagesize": 3,
    }
    if _APP_KEY:
        params["key"] = _APP_KEY

    answers_by_qid: dict[int, list[dict]] = {}
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
            url = f"{_BASE_URL}/questions/{ids_str}/answers"
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()

        for ans in data.get("items", []):
            if ans.get("score", 0) < _MIN_ANSWER_SCORE:
                continue
            qid = ans.get("question_id", 0)
            answers_by_qid.setdefault(qid, []).append(ans)

    except Exception as e:
        logger.debug(f"[stackoverflow] answer fetch error: {e}")

    return answers_by_qid


# ═══════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════

import html as html_module
import re

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html_module.unescape(_TAG_RE.sub(" ", text)).strip()


def _format_results(
    questions: list[dict],
    answers: dict[int, list[dict]],
    query: str,
) -> str:
    lines = [f"[STACK OVERFLOW Q&A]", f"Query: {query}", ""]
    for i, q in enumerate(questions, 1):
        qid   = q.get("question_id", 0)
        title = q.get("title", "Untitled")
        score = q.get("score", 0)
        tags  = ", ".join(q.get("tags", [])[:5])
        link  = q.get("link", f"https://stackoverflow.com/q/{qid}")
        lines.append(f"{i}. {title}")
        lines.append(f"   Score: {score} | Tags: {tags}")
        lines.append(f"   {link}")

        q_answers = answers.get(qid, [])
        if q_answers:
            top = q_answers[0]
            body = _strip_html(top.get("body", ""))[:400]
            is_accepted = "✓ Accepted" if top.get("is_accepted") else f"Score: {top.get('score', 0)}"
            lines.append(f"   [{is_accepted}] {body}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Cache Helpers
# ═══════════════════════════════════════════════════════════════════

def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="stackoverflow", max_age_hours=_CACHE_TTL_HOURS)
    except Exception:
        return None


async def _store_cached(
    q_hash: str, source: str, query: str, result: str, state: "PipelineState"
) -> None:
    try:
        from factory.memory.mother_memory import store_scout_cache
        await store_scout_cache(
            query_hash=q_hash, source=source,
            query_preview=query[:80], result_preview=result[:600],
            urls=[], operator_id=state.operator_id or "",
            project_id=state.project_id,
        )
    except Exception:
        pass
