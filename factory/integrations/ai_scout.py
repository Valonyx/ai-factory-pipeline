"""
AI Factory Pipeline v5.8 — AI Scout (Always-Free LLM Research Fallback)

When all external search APIs (Perplexity, Tavily, DuckDuckGo, Exa,
Wikipedia, HackerNews) are exhausted or unavailable, the pipeline routes
Scout queries through the existing AI provider chain as a research assistant.

This is never "offline" — it works as long as any free AI provider is up.

Enhancements over original:
  • Full AI chain support — Gemini, Groq, OpenRouter, Cerebras, Together,
    Mistral, Anthropic (Haiku). All providers now work in raw research mode.
  • Domain-specific system prompts — legal expert vs tech expert vs market
    analyst vs factual researcher. Query domain is auto-detected from the
    query text, producing more accurate and focused research responses.
  • Mother Memory context injection — pulls the last 5 relevant Scout
    insights from memory before answering, so the AI research assistant
    has institutional context about the project.
  • Structured output — findings are numbered with confidence indicators
    and dated knowledge-cutoff warnings.
  • Memory storage — successful results cached for later reuse.

Cost: $0.00 — uses existing free AI provider tiers.

Spec Authority: v5.6 §2.2.3, §2.10
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.ai_scout")

AI_SCOUT_COST_PER_CALL: float = 0.0
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))

# ═══════════════════════════════════════════════════════════════════
# Domain-Specific System Prompts
# ═══════════════════════════════════════════════════════════════════

_SYSTEM_PROMPTS: dict[str, str] = {

    "legal": """\
You are a legal research specialist with deep expertise in Saudi Arabian \
technology law and international data protection regulations. \
You know PDPL (Saudi Personal Data Protection Law), SAMA regulations, \
CST (Communications, Space & Technology Commission) requirements, \
NCA cybersecurity regulations, NDMO data governance policies, \
SDAIA AI governance, and Apple/Google App Store legal requirements.

Research guidelines:
- Cite specific law articles, regulation numbers, and official bodies
- Distinguish between mandatory requirements and recommendations
- Note compliance deadlines and grace periods where known
- Flag areas where Saudi law diverges from GDPR or other frameworks
- State your knowledge cutoff clearly and flag anything that may have changed
- Never fabricate regulation text — say "may require verification" when uncertain""",

    "tech": """\
You are a senior software engineer and architect with expertise in mobile \
and web development. You specialise in React Native, Flutter/FlutterFlow, \
Swift/iOS, Kotlin/Android, Next.js, FastAPI, and cloud deployment on GCP/AWS.

Research guidelines:
- Provide version-specific answers when versions matter
- Distinguish stable API from experimental/deprecated features
- Reference official documentation titles and sections (not URLs you cannot verify)
- Note breaking changes and migration paths
- Flag anything that may have changed after your knowledge cutoff (mid-2024)
- For security-related technical questions, err on the side of caution""",

    "market": """\
You are a mobile app market analyst specialising in the MENA region, \
with a focus on Saudi Arabia and the GCC. You track app store trends, \
competitor landscapes, user behaviour, and monetisation models.

Research guidelines:
- Provide specific competitor names, features, and market positions
- Give realistic user/revenue estimates based on available benchmarks
- Note regional preferences (Arabic UI, local payment methods, etc.)
- Flag data points that are estimates vs. reported figures
- Keep analysis grounded — no fabricated market share percentages""",

    "community": """\
You are a knowledgeable senior developer and community observer. \
You synthesise developer community sentiment, best practices, \
and real-world experience reports from sources like HackerNews, \
Stack Overflow, Reddit, and official developer blogs.

Research guidelines:
- Represent the range of developer opinions fairly
- Distinguish community consensus from minority views
- Note when opinions are time-sensitive (e.g., about a fast-moving library)
- Cite the type of source (not a URL) — e.g., "HN community generally reports..."
- Be honest when the community is divided""",

    "factual": """\
You are a precise factual researcher. You provide clear, accurate \
definitions, explanations, and overviews drawn from your training on \
technical documentation, encyclopaedic sources, and reference materials.

Research guidelines:
- Lead with the direct answer, then explain
- Use precise technical terminology
- Cite standard bodies when relevant (ISO, IEEE, IETF RFC numbers, etc.)
- Distinguish well-established facts from evolving standards
- Flag your knowledge cutoff for anything that may have changed""",

    "general": """\
You are a research assistant specialising in market intelligence, \
regulatory requirements, app store guidelines, and technology landscape \
analysis. Answer research questions based on your training knowledge.

Research guidelines:
- Lead with a direct answer
- List 3–5 key findings with supporting detail
- Note the knowledge cutoff where relevant (training ends mid-2024)
- Flag areas where information may have changed recently
- Be specific: cite regulations by name, frameworks by version
- If uncertain, say so rather than guessing""",
}

# ═══════════════════════════════════════════════════════════════════
# Research Prompt Template
# ═══════════════════════════════════════════════════════════════════

_RESEARCH_TEMPLATE = """\
{prior_context}\
[AI-SCOUT RESEARCH REQUEST — domain: {domain}]

Research question: {query}

Project context: {context}

Provide a structured research summary:

RESEARCH SUMMARY: {query_short}

KEY FINDINGS:
1. [Finding with specific detail and confidence level]
2. [Finding with specific detail and confidence level]
3. [Finding with specific detail and confidence level]
(continue as needed)

KNOWLEDGE CURRENCY:
[Note what may have changed since your training cutoff and what needs live verification]

SOURCES REFERENCED:
[Name any specific documents, standards, or bodies you drew from — do not fabricate URLs]
"""

# ═══════════════════════════════════════════════════════════════════
# Domain detection (lightweight, mirrors scout_orchestrator)
# ═══════════════════════════════════════════════════════════════════

_DOMAIN_HINTS: dict[str, list[str]] = {
    "legal":     ["regulation", "compliance", "pdpl", "sama", "cst", "nca", "ndmo",
                  "sdaia", "law", "license", "privacy policy", "gdpr", "hipaa", "pci"],
    "tech":      ["framework", "library", "sdk", "api", "version", "deprecated",
                  "react", "flutter", "swift", "kotlin", "npm", "github", "dependency"],
    "market":    ["competitor", "market", "trending", "popular", "revenue", "users",
                  "app store ranking", "monetize", "pricing"],
    "community": ["community", "opinion", "recommend", "vs", "versus", "prefer",
                  "best practice", "should i"],
    "factual":   ["what is", "define", "explain", "overview", "history", "who is"],
}


def _detect_domain(query: str) -> str:
    q = query.lower()
    for domain, hints in _DOMAIN_HINTS.items():
        if any(h in q for h in hints):
            return domain
    return "general"


def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════
# Memory Context Injection
# ═══════════════════════════════════════════════════════════════════

async def _pull_prior_research(
    query: str,
    state: "PipelineState",
) -> str:
    """Pull the last 5 relevant Scout cache entries from Mother Memory.

    Gives the AI research assistant institutional context so it doesn't
    repeat work already done in this project.
    """
    try:
        from factory.memory.mother_memory import get_recent_insights
        insights = await get_recent_insights(
            operator_id=state.operator_id or "system",
            limit=8,
        )
        relevant = [
            i for i in insights
            if i.get("insight_type") == "scout_cache"
            and i.get("project_id") == state.project_id
        ][:5]

        if not relevant:
            return ""

        lines = ["[PRIOR RESEARCH from Mother Memory for this project]"]
        for r in relevant:
            content = r.get("content", "")
            # Strip the SCOUT_CACHE:{hash}:{source}: prefix
            parts = content.split(":", 3)
            if len(parts) == 4:
                lines.append(f"  [{parts[2]}] {parts[3][:200]}")
            else:
                lines.append(f"  {content[:200]}")
        lines.append("")
        return "\n".join(lines) + "\n"
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

async def call_ai_scout(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query using the AI provider chain.

    Includes domain detection, memory context injection, domain-specific
    system prompts, and structured output.

    Returns (formatted_results, cost_usd).
    """
    from factory.integrations.provider_chain import ai_chain

    query = prompt.strip()[:500]
    q_hash = _query_hash(query)

    # ── Cache check ───────────────────────────────────────────────────
    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[ai-scout] cache hit for '{query[:60]}'")
        return cached, AI_SCOUT_COST_PER_CALL

    # ── Detect domain ─────────────────────────────────────────────────
    domain = _detect_domain(query)
    system_prompt = _SYSTEM_PROMPTS.get(domain, _SYSTEM_PROMPTS["general"])

    # ── Pull prior research from Mother Memory ─────────────────────────
    prior_context = await _pull_prior_research(query, state)

    # ── Build research prompt ──────────────────────────────────────────
    context = f"App: {state.app_name or 'N/A'}, Stack: {state.tech_stack or 'N/A'}"
    full_prompt = (
        f"{system_prompt}\n\n"
        + _RESEARCH_TEMPLATE.format(
            prior_context=prior_context,
            domain=domain,
            query=query,
            query_short=query[:80],
            context=context,
        )
    )

    # ── Try AI providers ───────────────────────────────────────────────
    tried: set[str] = set()
    for _ in range(len(ai_chain.chain)):
        provider = ai_chain.get_active()
        if provider in tried:
            break
        tried.add(provider)

        try:
            response = await _call_provider_raw(provider, full_prompt)
            if response and not response.startswith("[MOCK"):
                formatted = f"[AI-SCOUT via {provider} | domain={domain}]\n\n{response}"

                # ── Cache result ──────────────────────────────────────
                await _store_cached(q_hash, f"ai_scout/{provider}", query, formatted, [], state)

                ai_chain.mark_success(provider)
                logger.info(f"[ai-scout] answered via {provider} (domain={domain})")
                return formatted, AI_SCOUT_COST_PER_CALL

        except Exception as e:
            err = str(e)
            from factory.integrations.provider_chain import is_quota_error, is_auth_error
            if is_quota_error(err):
                ai_chain.mark_quota_exhausted(provider)
            elif is_auth_error(err):
                ai_chain.mark_error(provider, f"auth: {err[:60]}")
            else:
                ai_chain.mark_error(provider, err[:60])

    logger.warning(f"[ai-scout] all AI providers exhausted for {state.project_id}")
    return (
        f"[AI-SCOUT-UNAVAILABLE] All AI providers currently exhausted. "
        f"Query: {query[:100]}. "
        f"Retry when quota resets (use /providers for reset times).",
        AI_SCOUT_COST_PER_CALL,
    )


# ═══════════════════════════════════════════════════════════════════
# Provider Raw Calls (full chain — now includes Gemini + Anthropic)
# ═══════════════════════════════════════════════════════════════════

async def _call_provider_raw(provider: str, prompt: str) -> str:
    """Call a provider in lightweight raw mode (no RoleContract).

    All providers in the AI chain are now supported, including Gemini
    and Anthropic (Haiku), which previously required a RoleContract.
    """
    max_tokens   = 1400
    temperature  = 0.3   # low temperature for factual research

    if provider == "gemini":
        from factory.integrations.gemini import _call_gemini_raw
        return await _call_gemini_raw(prompt, max_tokens=max_tokens, temperature=temperature)

    if provider == "anthropic":
        return await _call_anthropic_raw(prompt, max_tokens=max_tokens)

    if provider == "groq":
        from factory.integrations.groq_provider import call_groq_raw
        return await call_groq_raw(prompt, max_tokens=max_tokens, temperature=temperature)

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

    raise ValueError(f"[ai-scout] Provider {provider!r} not supported")


async def _call_anthropic_raw(prompt: str, max_tokens: int = 1400) -> str:
    """Call Anthropic Claude Haiku in raw mode for AI Scout research."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    import anthropic as sdk
    client = sdk.AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",  # cheapest Anthropic model
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        raise ValueError("Anthropic returned empty response")
    return text


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="ai_scout", max_age_hours=_CACHE_TTL_HOURS)
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
