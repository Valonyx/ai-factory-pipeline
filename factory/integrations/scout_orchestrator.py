"""
AI Factory Pipeline v5.8 — Scout Orchestrator

The intelligence layer that sits between roles.py and every Scout provider.
Replaces the naïve "try each provider until one works" waterfall with a
smart, memory-aware, query-adaptive research engine.

What it adds over the old chain loop:

  QueryClassifier
    Analyses every query and builds a QueryProfile: domain (legal / tech /
    market / community / factual / general), stakes level (high / normal / low),
    freshness requirement (realtime / recent / any), and KSA-specificity flag.

  Domain-Aware Provider Routing
    Different query types have different best providers. A legal query should
    hit Perplexity → Exa → Wikipedia first. A tech query should hit Exa →
    HackerNews → Tavily first. The fallback waterfall only triggers after
    domain-optimal providers are exhausted.

  Parallel Fusion for High-Stakes Queries
    Legal and compliance queries run the top-two providers in parallel.
    If both succeed, an AI synthesis call cross-references them, marks
    consensus findings as [CONFIRMED ✓] and conflicts as [CONFLICTING ⚠].
    This is the strongest accuracy mechanism in the pipeline.

  Shared Mother Memory Cache (all providers)
    All providers share one cache namespace. The cache is checked BEFORE
    any API call. TTL is configurable (default 4h). Hitting the cache saves
    quota for every provider, not just Exa.

  Confidence Scoring
    Every result gets a calibrated confidence score (0.0–1.0) based on:
    provider base score, grounding success, fusion bonus, result richness,
    and absence of [UNVERIFIED] markers.

  Telegram Notifications
    When a high-stakes research call produces low-confidence results, the
    operator receives a brief warning via Telegram — without blocking the
    pipeline.

Spec Authority: v5.6 §2.2.3, §2.10, §5.4
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.scout_orchestrator")

# ═══════════════════════════════════════════════════════════════════
# Query Classification
# ═══════════════════════════════════════════════════════════════════

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "legal": [
        "regulation", "compliance", "legal", "pdpl", "sama", "cst", "nca",
        "ndmo", "sdaia", "law", "license", "permit", "privacy policy",
        "terms of service", "gdpr", "hipaa", "pci", "ministry", "authority",
        "requirement", "prohibited", "banned", "sanction", "fine", "penalty",
        "data protection", "cross-border data", "user data", "consent",
        "app store review", "apple guideline", "google play policy",
        "section 3.1", "section 4.2", "in-app purchase policy", "rejection",
    ],
    "tech": [
        "framework", "library", "sdk", "api", "version", "deprecated",
        "bug", "changelog", "release notes", "npm", "github", "pypi",
        "react", "flutter", "swift", "kotlin", "next.js", "fastapi",
        "package", "dependency", "migration", "upgrade", "compatibility",
        "breaking change", "import", "module", "cve", "security patch",
        "docker", "kubernetes", "deployment", "ci/cd", "build error",
    ],
    "market": [
        "competitor", "competing app", "market", "trending", "popular",
        "app store ranking", "revenue", "monetize", "pricing", "plan",
        "user growth", "market share", "alternative", "comparison",
        "top app", "best app", "leading", "unicorn", "startup",
    ],
    "community": [
        "community opinion", "experience with", "recommend", "should i use",
        "vs", "versus", "prefer", "best practice", "advice", "review",
        "forum", "discussion", "thread", "people say", "developer",
    ],
    "factual": [
        "what is", "define", "definition", "explain", "overview",
        "history of", "who is", "when was", "founded", "standard",
        "specification", "rfc", "iso", "ieee", "how does", "architecture",
    ],
}

_HIGH_STAKES_KEYWORDS: list[str] = [
    "pdpl", "sama", "cst", "nca", "ndmo", "sdaia",
    "compliance", "legal requirement", "regulation", "regulatory",
    "prohibited", "banned", "license required",
    "apple app store", "google play", "app store review", "rejected",
    "gdpr", "hipaa", "pci", "security standard",
    "data protection", "cross-border", "financial regulation",
    "owasp", "encryption", "ssl", "tls",
]

_KSA_KEYWORDS: list[str] = [
    "ksa", "saudi", "riyadh", "jeddah", "makkah", "madinah",
    "pdpl", "sama", "cst", "nca", "ndmo", "sdaia",
    "saudi arabia", "kingdom of saudi", "ksa regulation",
]

_REALTIME_KEYWORDS: list[str] = [
    "latest", "current", "today", "recent", "news", "new release",
    "just released", "announcement", "update", "2025", "2026",
    "this week", "this month", "breaking",
]

# Best provider order per domain (highest-affinity first).
# Unlimited providers (∞) are listed after quota-limited ones to preserve
# monthly budget while still providing broad coverage as fallbacks.
_PROVIDER_ORDER: dict[str, list[str]] = {
    "legal": [
        "perplexity",   # AI-synthesised authoritative answers
        "exa",          # neural semantic search + real-crawl
        "wikipedia",    # encyclopedic legal/regulatory definitions
        "tavily",       # web synthesis
        "brave",        # independent index, cross-check
        "searxng",      # meta-search (DDG+Google+Bing aggregated)
        "duckduckgo",   # keyword fallback
        "ai_scout",     # LLM knowledge as final fallback
    ],
    "tech": [
        "exa",          # neural code/doc search
        "stackoverflow", # accepted answers from devs
        "github_search", # real-world implementations
        "hackernews",   # bleeding-edge community signals
        "tavily",       # web synthesis
        "searxng",      # meta-search fallback
        "duckduckgo",   # keyword fallback
        "reddit",       # developer community opinions
        "ai_scout",     # LLM knowledge
    ],
    "market": [
        "perplexity",   # synthesised market intelligence
        "tavily",       # web synthesis
        "brave",        # independent index
        "exa",          # semantic search
        "reddit",       # community/user sentiment
        "hackernews",   # startup/tech community
        "searxng",      # meta-search
        "duckduckgo",   # keyword fallback
        "ai_scout",     # LLM knowledge
    ],
    "community": [
        "hackernews",   # tech community discussions
        "reddit",       # broader community insights
        "stackoverflow", # dev community Q&A
        "duckduckgo",   # keyword search
        "searxng",      # meta-search
        "tavily",       # web synthesis
        "ai_scout",     # LLM synthesis
    ],
    "factual": [
        "wikipedia",    # encyclopedic facts
        "exa",          # semantic search
        "brave",        # independent web index
        "tavily",       # web synthesis
        "searxng",      # meta-search
        "duckduckgo",   # keyword fallback
        "ai_scout",     # LLM knowledge
    ],
    "general": [
        "perplexity",   # best all-round quality
        "tavily",       # AI-synthesised web search
        "exa",          # neural semantic search
        "brave",        # independent index
        "searxng",      # meta-search aggregator
        "duckduckgo",   # keyword search
        "wikipedia",    # encyclopedic facts
        "hackernews",   # tech community
        "reddit",       # community discussions
        "stackoverflow", # dev Q&A
        "github_search", # code/repo landscape
        "ai_scout",     # LLM fallback
    ],
}

# Base confidence per provider (calibrated against empirical quality).
# These scores reflect the provider's typical factual accuracy and
# source quality, NOT availability. Scores are adjusted up/down
# at runtime by the confidence scorer (grounding, fusion, text richness).
_BASE_CONFIDENCE: dict[str, float] = {
    "perplexity":  0.90,
    "exa":         0.85,
    "wikipedia":   0.80,
    "tavily":      0.75,
    "brave":       0.72,
    "stackoverflow": 0.70,
    "github_search": 0.65,
    "hackernews":  0.65,
    "searxng":     0.62,
    "duckduckgo":  0.60,
    "reddit":      0.55,
    "ai_scout":    0.50,
}


@dataclass
class QueryProfile:
    domain: str              # legal | tech | market | community | factual | general
    stakes: str              # high | normal | low
    freshness: str           # realtime | recent | any
    ksa_specific: bool       # True → KSA-aware search (domains filter etc.)
    provider_order: list[str] = field(default_factory=list)


@dataclass
class ScoutResult:
    content: str
    provider: str            # winning provider (or "p1+p2" for fused)
    confidence: float        # 0.0–1.0 calibrated score
    grounded: bool           # Exa grounding was applied
    fused: bool              # multi-source AI synthesis was applied
    cost: float
    cached: bool
    domain: str
    query_hash: str
    urls: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════

class ScoutOrchestrator:
    """Intelligent Scout research engine.

    Usage (singleton via get_scout_orchestrator()):
        orch = get_scout_orchestrator()
        text, cost = await orch.research(prompt, state, contract)
    """

    # Confidence below this for a high-stakes result triggers Telegram warning
    _LOW_CONFIDENCE_THRESHOLD: float = 0.55

    # ── Query Classification ──────────────────────────────────────────

    def classify(self, query: str) -> QueryProfile:
        """Classify query into a QueryProfile that drives routing decisions."""
        q = query.lower()

        # Domain detection (first match wins — order matters)
        domain = "general"
        for dom, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in q for kw in keywords):
                domain = dom
                break

        # Stakes detection (independent of domain)
        stakes = "high" if any(kw in q for kw in _HIGH_STAKES_KEYWORDS) else "normal"

        # Freshness
        freshness = "realtime" if any(kw in q for kw in _REALTIME_KEYWORDS) else "any"

        # KSA specificity
        ksa_specific = any(kw in q for kw in _KSA_KEYWORDS)

        # Build ordered provider list for this domain
        base_order = _PROVIDER_ORDER.get(domain, _PROVIDER_ORDER["general"])

        return QueryProfile(
            domain=domain,
            stakes=stakes,
            freshness=freshness,
            ksa_specific=ksa_specific,
            provider_order=base_order,
        )

    def _available_providers(
        self,
        profile: QueryProfile,
    ) -> list[str]:
        """Return profile.provider_order filtered to chain-available providers.

        Providers at ≥80% monthly quota are moved to the end of the list
        (still available but deprioritised) to spread quota load across
        providers before any single one exhausts.
        """
        from factory.integrations.provider_chain import scout_chain, quota_tracker

        # Check and apply any time-based quota resets
        for name in scout_chain.chain:
            scout_chain.statuses[name].check_reset()

        available = {
            name for name, st in scout_chain.statuses.items() if st.available
        }
        # Providers that are always free with no meaningful quota limit
        no_quota = {
            "wikipedia", "hackernews", "ai_scout",
            "searxng", "duckduckgo", "reddit", "github_search",
        }

        # Split into normal vs. deprioritised (≥80% quota used)
        normal: list[str] = []
        deprioritized: list[str] = []

        for p in profile.provider_order:
            if p not in available and p not in no_quota:
                continue  # hard-exhausted or unavailable — skip
            if quota_tracker.should_deprioritize(p):
                deprioritized.append(p)
            else:
                normal.append(p)

        # Deprioritised providers come AFTER normal ones, preserving their
        # relative order among themselves
        return normal + deprioritized

    # ── Cache helpers ─────────────────────────────────────────────────

    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.md5(query.strip().lower().encode()).hexdigest()[:16]

    async def _check_cache(
        self, q_hash: str, source_filter: str = "",
    ) -> Optional[str]:
        try:
            from factory.memory.mother_memory import get_cached_scout_result
            return await get_cached_scout_result(
                query_hash=q_hash,
                source=source_filter,
                max_age_hours=int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4")),
            )
        except Exception:
            return None

    async def _store_cache(
        self,
        q_hash: str,
        result: ScoutResult,
        state: "PipelineState",
    ) -> None:
        try:
            from factory.memory.mother_memory import store_scout_cache
            await store_scout_cache(
                query_hash=q_hash,
                source=result.provider,
                query_preview=result.query_hash,  # reuse hash as preview key
                result_preview=result.content[:600],
                urls=result.urls,
                operator_id=state.operator_id or "",
                project_id=state.project_id,
            )
        except Exception:
            pass

    # ── Provider call wrappers ────────────────────────────────────────

    async def _try_provider(
        self,
        provider: str,
        query: str,
        contract: "RoleContract",
        state: "PipelineState",
        domain: str = "general",
    ) -> tuple[str, float]:
        """Call one Scout provider, managing chain state on errors."""
        from factory.integrations.provider_chain import (
            scout_chain, quota_tracker, is_quota_error, is_auth_error, parse_retry_delay,
        )
        from factory.core.roles import _call_single_scout_provider
        try:
            result = await _call_single_scout_provider(
                provider, query, contract, state, domain=domain,
            )
            scout_chain.mark_success(provider)
            quota_tracker.record_use(provider)
            return result
        except Exception as e:
            err = str(e)
            if is_quota_error(err):
                scout_chain.mark_quota_exhausted(provider, parse_retry_delay(err))
                logger.info(f"[scout-orch] {provider} quota exhausted")
            elif is_auth_error(err):
                scout_chain.mark_error(provider, f"auth: {err[:60]}")
            else:
                scout_chain.mark_error(provider, err[:60])
            raise

    # ── Sequential waterfall ──────────────────────────────────────────

    async def _sequential(
        self,
        providers: list[str],
        query: str,
        contract: "RoleContract",
        state: "PipelineState",
        domain: str,
    ) -> Optional[ScoutResult]:
        for provider in providers:
            try:
                text, cost = await self._try_provider(provider, query, contract, state, domain=domain)
                confidence = self._score_confidence(
                    provider, text, grounded=False, fused=False,
                )
                return ScoutResult(
                    content=text,
                    provider=provider,
                    confidence=confidence,
                    grounded=False,
                    fused=False,
                    cost=cost,
                    cached=False,
                    domain=domain,
                    query_hash=self._query_hash(query),
                    urls=_extract_urls(text),
                )
            except Exception:
                continue
        return None

    # ── Parallel fusion ───────────────────────────────────────────────

    async def _parallel_fuse(
        self,
        providers: list[str],
        query: str,
        contract: "RoleContract",
        state: "PipelineState",
        domain: str,
    ) -> Optional[ScoutResult]:
        """Run top-2 providers in parallel; fuse if both succeed."""
        if len(providers) < 2:
            return await self._sequential(providers, query, contract, state, domain)

        p1, p2 = providers[0], providers[1]

        r1_task = asyncio.create_task(self._try_provider(p1, query, contract, state, domain=domain))
        r2_task = asyncio.create_task(self._try_provider(p2, query, contract, state, domain=domain))
        results = await asyncio.gather(r1_task, r2_task, return_exceptions=True)

        r1 = results[0] if not isinstance(results[0], Exception) else None
        r2 = results[1] if not isinstance(results[1], Exception) else None

        if r1 and r2:
            # Both succeeded — synthesize via AI
            fused_text, fused_cost = await self._fuse(r1, r2, p1, p2, query, state)
            confidence = self._score_confidence(
                f"{p1}+{p2}", fused_text, grounded=False, fused=True,
            )
            return ScoutResult(
                content=fused_text,
                provider=f"{p1}+{p2}",
                confidence=confidence,
                grounded=False,
                fused=True,
                cost=(r1[1] + r2[1] + fused_cost),
                cached=False,
                domain=domain,
                query_hash=self._query_hash(query),
                urls=_extract_urls(fused_text),
            )

        # One succeeded
        for r, pname in [(r1, p1), (r2, p2)]:
            if r:
                confidence = self._score_confidence(pname, r[0], grounded=False, fused=False)
                return ScoutResult(
                    content=r[0],
                    provider=pname,
                    confidence=confidence,
                    grounded=False,
                    fused=False,
                    cost=r[1],
                    cached=False,
                    domain=domain,
                    query_hash=self._query_hash(query),
                    urls=_extract_urls(r[0]),
                )

        # Both failed — fall through to remaining providers
        remaining = [p for p in providers[2:]]
        return await self._sequential(remaining, query, contract, state, domain)

    # ── AI synthesis (fusion) ─────────────────────────────────────────

    async def _fuse(
        self,
        r1: tuple[str, float],
        r2: tuple[str, float],
        p1: str,
        p2: str,
        query: str,
        state: "PipelineState",
    ) -> tuple[str, float]:
        """Synthesise two independent Scout results into a single grounded answer."""
        synthesis_prompt = (
            f"You are a research synthesis specialist. Combine two independent "
            f"research results on the same query into one authoritative summary.\n\n"
            f"ORIGINAL QUERY: {query[:300]}\n\n"
            f"SOURCE A [{p1.upper()}]:\n{r1[0][:1400]}\n\n"
            f"SOURCE B [{p2.upper()}]:\n{r2[0][:1400]}\n\n"
            f"SYNTHESIS INSTRUCTIONS:\n"
            f"1. Lead with facts confirmed by BOTH sources — mark [CONFIRMED ✓]\n"
            f"2. Include important unique findings from each source separately\n"
            f"3. Mark contradictions [CONFLICTING ⚠ — verify manually]\n"
            f"4. Collect all source URLs at the end under SOURCES:\n"
            f"5. Be concise — under 700 words\n"
            f"6. Never fabricate — only synthesise what the sources say\n\n"
            f"SYNTHESIZED RESEARCH SUMMARY:"
        )
        try:
            text = await _call_ai_for_synthesis(synthesis_prompt)
            if text and not text.startswith("["):
                header = f"[FUSED: {p1}+{p2}]\n\n"
                return header + text, 0.0
        except Exception as e:
            logger.debug(f"[scout-orch] fusion AI call failed: {e} — concatenating")

        # Fallback: simple concatenation with clear labelling
        combined = (
            f"[FUSED: {p1}+{p2}]\n\n"
            f"─── Source A: {p1.upper()} ───\n{r1[0][:1000]}\n\n"
            f"─── Source B: {p2.upper()} ───\n{r2[0][:1000]}"
        )
        return combined, 0.0

    # ── Confidence scoring ────────────────────────────────────────────

    @staticmethod
    def _score_confidence(
        provider: str,
        text: str,
        grounded: bool,
        fused: bool,
    ) -> float:
        base_provider = provider.split("+")[0] if "+" in provider else provider
        score = _BASE_CONFIDENCE.get(base_provider, 0.55)

        if fused:             score += 0.08
        if grounded:          score += 0.10
        if "[UNVERIFIED]" in text:  score -= 0.15
        if len(text) > 600:   score += 0.04
        if len(text) < 150:   score -= 0.08

        # Count source URLs as quality signal
        url_count = len(re.findall(r"https?://\S+", text))
        if url_count >= 3:    score += 0.03
        if url_count == 0:    score -= 0.05

        return round(max(0.0, min(1.0, score)), 2)

    # ── Main entry point ──────────────────────────────────────────────

    async def research(
        self,
        query: str,
        state: "PipelineState",
        contract: "RoleContract",
    ) -> tuple[str, float]:
        """Run intelligent Scout research and return (content, cost).

        This is the single entry point called by roles._call_perplexity_safe.
        """
        q_hash = self._query_hash(query)

        # ── 1. Check Mother Memory cache ──────────────────────────────
        cached_text = await self._check_cache(q_hash)
        if cached_text:
            logger.info(f"[scout-orch] cache HIT for project={state.project_id}")
            state.project_metadata["_last_scout_grounding"] = {
                "confidence": 0.70,
                "source": "cache",
                "grounded": False,
                "prompt_preview": query[:60],
            }
            return cached_text, 0.0

        # ── 2. Classify query ─────────────────────────────────────────
        profile = self.classify(query)
        logger.info(
            f"[scout-orch] query classified: domain={profile.domain} "
            f"stakes={profile.stakes} ksa={profile.ksa_specific} "
            f"freshness={profile.freshness}"
        )

        # ── 3. Route to available providers ───────────────────────────
        providers = self._available_providers(profile)
        if not providers:
            providers = ["ai_scout"]  # guaranteed fallback

        # ── 4. Execute research ───────────────────────────────────────
        result: Optional[ScoutResult] = None

        if profile.stakes == "high" and len(providers) >= 2:
            # Parallel fusion for maximum accuracy
            result = await self._parallel_fuse(
                providers, query, contract, state, profile.domain,
            )
        else:
            result = await self._sequential(
                providers, query, contract, state, profile.domain,
            )

        if result is None:
            logger.error(f"[scout-orch] all providers failed for {state.project_id}")
            return (
                f"[SCOUT-EXHAUSTED] All providers failed for: {query[:80]}",
                0.0,
            )

        # ── 5. Exa grounding for high-stakes ─────────────────────────
        if profile.stakes == "high" and "exa" not in result.provider:
            try:
                from factory.integrations.exa_grounding import (
                    should_ground, ground_research,
                )
                if should_ground(query, result.provider):
                    grounded_text, grounding_conf = await ground_research(
                        raw_scout_output=result.content,
                        original_query=query,
                        state=state,
                        scout_source=result.provider,
                    )
                    if grounding_conf > 0:
                        result.content = grounded_text
                        result.grounded = True
                        result.confidence = self._score_confidence(
                            result.provider, grounded_text,
                            grounded=True, fused=result.fused,
                        )
            except Exception as e:
                logger.debug(f"[scout-orch] grounding skipped: {e}")

        # ── 6. Store confidence metadata on state ─────────────────────
        state.project_metadata["_last_scout_grounding"] = {
            "confidence": result.confidence,
            "source": result.provider,
            "grounded": result.grounded,
            "fused": result.fused,
            "domain": result.domain,
            "prompt_preview": query[:60],
        }

        # ── 7. Cache result in Mother Memory ─────────────────────────
        await self._store_cache(q_hash, result, state)

        # ── 8. Telegram notification for low-confidence high-stakes ──
        if (profile.stakes == "high"
                and result.confidence < self._LOW_CONFIDENCE_THRESHOLD):
            await _notify_low_confidence(result, query, state)

        logger.info(
            f"[scout-orch] {state.project_id}: provider={result.provider} "
            f"domain={result.domain} confidence={result.confidence:.0%} "
            f"grounded={result.grounded} fused={result.fused} "
            f"cached={result.cached}"
        )

        return result.content, result.cost


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════

_orchestrator: Optional[ScoutOrchestrator] = None


def get_scout_orchestrator() -> ScoutOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ScoutOrchestrator()
    return _orchestrator


# ═══════════════════════════════════════════════════════════════════
# AI Synthesis Helper (used by _fuse)
# ═══════════════════════════════════════════════════════════════════

async def _call_ai_for_synthesis(prompt: str) -> str:
    """Call cheapest available AI provider for result fusion synthesis."""
    from factory.integrations.provider_chain import ai_chain, is_quota_error
    max_tokens = 900
    temperature = 0.2  # low temp for factual synthesis

    tried: set[str] = set()
    for _ in range(len(ai_chain.chain)):
        provider = ai_chain.get_active()
        if provider in tried:
            break
        tried.add(provider)

        try:
            if provider == "groq":
                from factory.integrations.groq_provider import call_groq_raw
                return await call_groq_raw(prompt, max_tokens=max_tokens, temperature=temperature)
            if provider == "gemini":
                from factory.integrations.gemini import _call_gemini_raw
                return await _call_gemini_raw(prompt, max_tokens=max_tokens)
            if provider == "openrouter":
                from factory.integrations.openrouter_provider import call_openrouter_raw
                return await call_openrouter_raw(prompt, max_tokens=max_tokens, temperature=temperature)
            if provider == "cerebras":
                from factory.integrations.cerebras_provider import call_cerebras_raw
                return await call_cerebras_raw(prompt, max_tokens=max_tokens, temperature=temperature)
            if provider == "together":
                from factory.integrations.together_provider import call_together_raw
                return await call_together_raw(prompt, max_tokens=max_tokens, temperature=temperature)
            if provider == "mistral":
                from factory.integrations.mistral_provider import call_mistral_raw
                return await call_mistral_raw(prompt, max_tokens=max_tokens, temperature=temperature)
        except Exception as e:
            err = str(e)
            if is_quota_error(err):
                ai_chain.mark_quota_exhausted(provider)
            else:
                ai_chain.mark_error(provider, err[:60])
            continue

    raise RuntimeError("No AI provider available for synthesis")


# ═══════════════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════════════

def _extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s\)\]\"'>]+", text)))[:10]


async def _notify_low_confidence(
    result: ScoutResult,
    query: str,
    state: "PipelineState",
) -> None:
    """Send Telegram warning when high-stakes research confidence is low."""
    try:
        from factory.telegram.notifications import notify_scout_confidence
        await notify_scout_confidence(
            state=state,
            provider=result.provider,
            domain=result.domain,
            confidence=result.confidence,
            query_preview=query[:120],
            grounded=result.grounded,
            fused=result.fused,
        )
    except Exception as e:
        logger.debug(f"[scout-orch] Telegram confidence notification skipped: {e}")
