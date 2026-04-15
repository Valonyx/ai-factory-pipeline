"""
AI Factory Pipeline v5.8 — Wikipedia Scout Provider

Uses the Wikipedia REST API. Free forever, no key, no quota.
Excellent for established facts, regulatory frameworks, standards,
technology definitions, and company/organisation overviews.

Enhancements:
  • Mother Memory cache — check before API, store after
  • Parallel summary fetching — all page summaries fetched concurrently
  • HTML cleaning — removes search-highlight spans from excerpts
  • Arabic Wikipedia fallback — for KSA regulatory terms (ar.wikipedia.org)
  • Better excerpt selection — summary → extract → description → excerpt

API: https://en.wikipedia.org/w/rest.php/v1/search/page
     https://en.wikipedia.org/w/rest.php/v1/page/{title}/summary

Spec Authority: v5.8 §2.2.3
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import urllib.parse
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.wikipedia_scout")

WIKIPEDIA_COST_PER_CALL: float = 0.0

_EN_SEARCH_URL  = "https://en.wikipedia.org/w/rest.php/v1/search/page"
_AR_SEARCH_URL  = "https://ar.wikipedia.org/w/rest.php/v1/search/page"
_EN_SUMMARY_URL = "https://en.wikipedia.org/w/rest.php/v1/page/{key}/summary"
_AR_SUMMARY_URL = "https://ar.wikipedia.org/w/rest.php/v1/page/{key}/summary"

_HEADERS = {
    "User-Agent": "AI-Factory-Pipeline/5.6 (research assistant)",
}

_KSA_ARABIC_TERMS: list[str] = [
    "pdpl", "sama", "cst", "nca", "ndmo", "sdaia",
    "نظام حماية", "هيئة الاتصالات", "المركزية",
]
_CACHE_TTL_HOURS: int = int(__import__("os").getenv("SCOUT_CACHE_TTL_HOURS", "4"))

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


def _clean_excerpt(text: str) -> str:
    """Strip HTML search-highlight spans and other tags from Wikipedia excerpts."""
    return _HTML_TAG_RE.sub("", text).strip()


def _needs_arabic(query: str) -> bool:
    """True when the query mentions KSA regulatory terms that have Arabic pages."""
    q = query.lower()
    return any(kw in q for kw in _KSA_ARABIC_TERMS)


async def call_wikipedia_scout(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via Wikipedia REST API.

    Returns (formatted_results, cost_usd).
    """
    query = prompt.strip()[:250]
    q_hash = _query_hash(query)

    # ── Cache check ───────────────────────────────────────────────────
    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[wikipedia] cache hit for '{query[:60]}'")
        return cached, 0.0

    try:
        async with httpx.AsyncClient(timeout=20, headers=_HEADERS) as client:

            # ── Search English Wikipedia ──────────────────────────────
            search_resp = await client.get(
                _EN_SEARCH_URL, params={"q": query, "limit": 5},
            )
            if search_resp.status_code == 429:
                raise Exception("429 RESOURCE_EXHAUSTED — Wikipedia rate limit")
            if search_resp.status_code != 200:
                raise Exception(f"Wikipedia HTTP {search_resp.status_code}")

            pages = search_resp.json().get("pages", [])

            # Optional: Arabic Wikipedia for KSA regulatory terms
            ar_pages: list[dict] = []
            if _needs_arabic(query):
                try:
                    ar_resp = await client.get(
                        _AR_SEARCH_URL, params={"q": query, "limit": 2},
                    )
                    if ar_resp.status_code == 200:
                        ar_pages = ar_resp.json().get("pages", [])[:2]
                except Exception:
                    pass

            if not pages and not ar_pages:
                return (
                    f"[WIKIPEDIA-SCOUT] No results found for: {query[:100]}",
                    WIKIPEDIA_COST_PER_CALL,
                )

            # ── Parallel summary fetches ──────────────────────────────
            top_en = pages[:3]
            summary_tasks = [
                _fetch_summary(client, page, lang="en") for page in top_en
            ] + [
                _fetch_summary(client, page, lang="ar") for page in ar_pages
            ]
            summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)

            # ── Format ────────────────────────────────────────────────
            lines = [f"[WIKIPEDIA-SCOUT] Research results for: {query[:100]}\n"]
            urls: list[str] = []

            for i, (page, summary) in enumerate(
                zip(top_en + ar_pages, summaries), 1
            ):
                title = page.get("title", "")
                key = page.get("key", title.replace(" ", "_"))
                lang = "ar" if page in ar_pages else "en"
                base = "ar.wikipedia.org" if lang == "ar" else "en.wikipedia.org"
                url = f"https://{base}/wiki/{urllib.parse.quote(key)}"

                extract = ""
                if isinstance(summary, dict):
                    extract = (
                        summary.get("extract", "")
                        or summary.get("description", "")
                    )[:500]
                elif isinstance(summary, Exception):
                    raw_exc = _clean_excerpt(page.get("excerpt", ""))
                    extract = raw_exc[:250] or page.get("description", "")[:200]

                desc = page.get("description", "")
                desc_str = f" — {desc}" if desc else ""
                lang_flag = " [AR]" if lang == "ar" else ""

                lines.append(
                    f"{i}. {title}{lang_flag}{desc_str}\n"
                    f"   {extract}\n"
                    f"   Source: {url}"
                )
                urls.append(url)

            # Remaining titles without summaries (4th+ page)
            for j, page in enumerate(pages[3:], len(top_en) + len(ar_pages) + 1):
                title = page.get("title", "")
                key = page.get("key", title.replace(" ", "_"))
                url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(key)}"
                desc = page.get("description", "")
                lines.append(f"{j}. {title}{' — ' + desc if desc else ''}\n   Source: {url}")
                urls.append(url)

            formatted = "\n\n".join(lines)

            await _store_cached(q_hash, "wikipedia", query, formatted, urls, state)

            logger.info(
                f"[wikipedia] {state.project_id}: {len(pages)} EN + {len(ar_pages)} AR "
                f"pages for '{query[:60]}'"
            )
            return formatted, WIKIPEDIA_COST_PER_CALL

    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            raise
        logger.error(f"[wikipedia] error: {e}")
        raise


async def _fetch_summary(
    client: httpx.AsyncClient,
    page: dict,
    lang: str,
) -> dict:
    """Fetch a single page summary; returns {} on failure."""
    base_url = _AR_SUMMARY_URL if lang == "ar" else _EN_SUMMARY_URL
    key = urllib.parse.quote(page.get("key", page.get("title", "").replace(" ", "_")))
    try:
        resp = await client.get(base_url.format(key=key))
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="wikipedia", max_age_hours=_CACHE_TTL_HOURS)
    except Exception:
        return None


async def _store_cached(
    q_hash: str, source: str, query: str, result: str,
    urls: list[str], state: "PipelineState",
) -> None:
    try:
        from factory.memory.mother_memory import store_scout_cache
        await store_scout_cache(
            query_hash=q_hash, source=source,
            query_preview=query[:80], result_preview=result[:600],
            urls=urls, operator_id=state.operator_id or "",
            project_id=state.project_id,
        )
    except Exception:
        pass
