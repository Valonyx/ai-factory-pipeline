"""
AI Factory Pipeline v5.8 — Exa Grounding (Anti-Hallucination Layer)

Problem: Scout providers (Perplexity, Tavily, DuckDuckGo, AI Scout) can
return hallucinated facts, stale citations, or confident-sounding errors —
especially for legal/regulatory and technical spec queries where precision
is critical.

Solution: After any Scout call returns, Exa Grounding runs a parallel
neural search on the same query and appends real, crawled source passages
that confirm (or contradict) the Scout's findings. The Strategist then
sees both the Scout's answer AND the raw Exa-sourced evidence.

What it provides:
  • [EXA-VERIFIED] — claim supported by an actual source page
  • [EXA-UNVERIFIED] — claim not corroborated by any retrieved source
  • GROUNDING CONFIDENCE % — fraction of results with substantive content
  • Real source URLs — for every verified claim

Triggers automatically for high-stakes queries:
  - KSA / international regulations (PDPL, SAMA, CST, NDMO, NCA, SDAIA)
  - App store compliance (Apple/Google rejection risk)
  - Security standards (OWASP, SSL/TLS, encryption)
  - Tech spec claims (framework versions, API changes, deprecations)
  - Any query from the legal pipeline stage (S1)

Does NOT trigger for:
  - General/conversational Scout queries
  - Queries when EXA_API_KEY is not set
  - When Exa's quota is exhausted
  - When the Scout result already came from Exa (already grounded)

Output is appended to the Scout result before it reaches the Strategist.

Spec Authority: v5.6 §2.2.3 [C5] (Research Degradation Policy),
               §4.2 (S1 Legal Gate anti-hallucination)
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.integrations.exa_grounding")

_EXA_SEARCH_URL = "https://api.exa.ai/search"

# ═══════════════════════════════════════════════════════════════════
# High-Stakes Query Detection
# ═══════════════════════════════════════════════════════════════════

# Any Scout result for queries matching these keywords is grounded.
# Ordered by specificity — first match wins for logging.
_GROUNDING_TRIGGERS: list[tuple[str, list[str]]] = [
    ("ksa_regulation",    ["pdpl", "sama", "cst", "ndmo", "nca", "sdaia",
                           "ministry of commerce", "ksa regulation", "saudi law",
                           "saudi arabia law", "زكاة", "هيئة الاتصالات"]),
    ("compliance",        ["compliance", "regulation", "regulatory", "legal requirement",
                           "data protection", "privacy law", "financial regulation",
                           "gdpr", "hipaa", "pci", "pci-dss"]),
    ("app_store",         ["apple app store", "google play", "app store review",
                           "play store policy", "rejection risk", "app review guideline",
                           "section 3.1", "section 4.2", "in-app purchase policy"]),
    ("security",          ["owasp", "ssl", "tls", "encryption standard", "cipher",
                           "certificate authority", "security requirement", "penetration test",
                           "vulnerability", "cve-"]),
    ("tech_spec",         ["deprecated", "breaking change", "migration guide",
                           "changelog", "api version", "compatibility matrix",
                           "release notes", "requires node", "minimum version"]),
    ("legal_doc",         ["terms of service", "privacy policy", "cookie policy",
                           "eula", "license agreement", "intellectual property"]),
]


def should_ground(prompt: str, scout_source: str) -> bool:
    """Return True if this Scout result should be grounded via Exa.

    Grounding is skipped when:
    - EXA_API_KEY is not set
    - The result already came from Exa (already grounded by definition)
    - The query contains no high-stakes keywords
    """
    if not os.getenv("EXA_API_KEY", ""):
        return False
    if scout_source in ("exa",):
        return False  # already grounded

    prompt_lower = prompt.lower()
    for _category, keywords in _GROUNDING_TRIGGERS:
        if any(kw in prompt_lower for kw in keywords):
            return True
    return False


def _get_trigger_category(prompt: str) -> str:
    """Return the matched grounding category name (for logging)."""
    prompt_lower = prompt.lower()
    for category, keywords in _GROUNDING_TRIGGERS:
        if any(kw in prompt_lower for kw in keywords):
            return category
    return "general"


# ═══════════════════════════════════════════════════════════════════
# Grounding Engine
# ═══════════════════════════════════════════════════════════════════

async def ground_research(
    raw_scout_output: str,
    original_query: str,
    state: "PipelineState",
    scout_source: str = "unknown",
) -> tuple[str, float]:
    """Append Exa-sourced verification block to any Scout research output.

    This is the anti-hallucination core. It:
    1. Runs Exa neural search on the same original query
    2. Extracts key sentences (highlights) from real source pages
    3. Appends a structured verification block to the Scout output
    4. Calculates a grounding confidence score
    5. Caches the grounded result in Mother Memory

    Returns (grounded_output, confidence_0_to_1).
    Never raises — grounding failures are non-fatal.
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return raw_scout_output, 0.0

    query = original_query.strip()[:300]
    category = _get_trigger_category(query)

    t_start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                _EXA_SEARCH_URL,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "num_results": 5,
                    "type": "auto",
                    "use_autoprompt": True,
                    "livecrawl": "fallback",
                    "contents": {
                        "highlights": {
                            "num_sentences": 4,
                            "highlights_per_url": 2,
                        },
                    },
                },
            )

        if r.status_code == 429:
            logger.warning("[exa-grounding] quota exhausted — skipping grounding")
            return raw_scout_output, 0.0
        if r.status_code == 401:
            logger.error("[exa-grounding] 401 Unauthorized — check EXA_API_KEY")
            return raw_scout_output, 0.0
        if r.status_code != 200:
            logger.warning(f"[exa-grounding] HTTP {r.status_code} — skipping grounding")
            return raw_scout_output, 0.0

        results = r.json().get("results", [])
        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        if not results:
            grounded = (
                raw_scout_output
                + "\n\n══ EXA GROUNDING: no corroborating sources found ══\n"
                + f"[EXA-UNVERIFIED] Query: {query[:100]}"
            )
            return grounded, 0.0

        # ── Build verification block ─────────────────────────────────────
        substantive = [r for r in results if r.get("highlights") or r.get("text")]
        confidence = round(len(substantive) / len(results), 2) if results else 0.0

        block_lines = [
            "\n\n╔══ EXA GROUNDING VERIFICATION ══",
            f"│ Query category : {category}",
            f"│ Scout source   : {scout_source}",
            f"│ Sources found  : {len(results)} | With content: {len(substantive)}",
            f"│ Confidence     : {int(confidence * 100)}%",
            f"│ Latency        : {elapsed_ms}ms",
            "│",
            "│ The following real sources were retrieved for this query.",
            "│ Cross-reference the Scout's claims against these passages.",
            "│",
        ]

        urls_found: list[str] = []

        for i, res in enumerate(results, 1):
            title = res.get("title", "Untitled")
            url = res.get("url", "")
            published = (res.get("publishedDate") or "")[:10]
            highlights = res.get("highlights") or []

            if not highlights:
                block_lines.append(f"│ [{i}] {title}")
                block_lines.append(f"│     (no passage extracted)")
                block_lines.append(f"│     URL: {url}")
            else:
                passages = " … ".join(h.strip() for h in highlights[:2])[:500]
                date_str = f" [{published}]" if published else ""
                block_lines.append(f"│ [{i}] {title}{date_str}")
                block_lines.append(f"│     \"{passages}\"")
                block_lines.append(f"│     URL: {url}")

            if url:
                urls_found.append(url)

            block_lines.append("│")

        block_lines.append("╚══ END EXA GROUNDING ══")

        grounding_block = "\n".join(block_lines)
        grounded_output = raw_scout_output + grounding_block

        # ── Cache grounded result in Mother Memory ───────────────────────
        try:
            from factory.memory.mother_memory import store_scout_cache
            from factory.integrations.exa_scout import _query_hash
            await store_scout_cache(
                query_hash=_query_hash(query),
                source=f"exa_grounding/{scout_source}",
                query_preview=query[:80],
                result_preview=grounded_output[:600],
                urls=urls_found,
                operator_id=state.operator_id or "",
                project_id=state.project_id,
            )
        except Exception:
            pass  # never block pipeline over cache write

        logger.info(
            f"[exa-grounding] {state.project_id}: grounded {scout_source} result "
            f"({len(results)} sources, {int(confidence * 100)}% confidence, {elapsed_ms}ms)"
        )

        return grounded_output, confidence

    except Exception as e:
        logger.warning(f"[exa-grounding] non-fatal error: {e}")
        return raw_scout_output, 0.0


# ═══════════════════════════════════════════════════════════════════
# Authoritative Source Finder (for S1 Legal Gate)
# ═══════════════════════════════════════════════════════════════════

async def find_authoritative_sources(
    topic: str,
    state: "PipelineState",
    num_results: int = 3,
) -> list[dict]:
    """Find real authoritative sources for a given legal/regulatory topic.

    Used by S1 Legal Gate to anchor compliance decisions to actual documents.
    Returns a list of {"title", "url", "key_passage", "date"} dicts.
    Never raises.
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                _EXA_SEARCH_URL,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": f"official {topic} requirements documentation",
                    "num_results": num_results,
                    "type": "neural",
                    "use_autoprompt": True,
                    "contents": {
                        "highlights": {"num_sentences": 3, "highlights_per_url": 1},
                    },
                },
            )

        if r.status_code != 200:
            return []

        sources = []
        for res in r.json().get("results", []):
            highlights = res.get("highlights") or []
            key_passage = highlights[0].strip() if highlights else ""
            sources.append({
                "title": res.get("title", ""),
                "url": res.get("url", ""),
                "key_passage": key_passage[:400],
                "date": (res.get("publishedDate") or "")[:10],
            })
        return sources

    except Exception as e:
        logger.debug(f"[exa-grounding] find_authoritative_sources error: {e}")
        return []
