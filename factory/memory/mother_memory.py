"""
AI Factory Pipeline v5.8 — Mother Memory (Unified Persistent Memory)

Everything the pipeline and the operator ever say or do is remembered here.
This is the single source of truth for all AI providers — so when the chain
switches from Gemini → Groq → Together AI, the new provider gets the same
full context as if it had been there from the start.

What is stored:
  OperatorMessage   — every Telegram message (user + bot), including off-topic
  PipelineDecision  — key choices made in pipeline stages (stack, legal, etc.)
  MemoryInsight     — extracted long-term facts worth remembering forever

Storage — 4-backend resilient chain (fan-out writes):
  1. Neo4j    (primary)   — graph DB, AuraDB Free, no daily limit
  2. Supabase (fallback1) — PostgreSQL REST, 500 MB free
  3. Upstash  (fallback2) — Redis REST, 10K commands/day (resets midnight UTC)
  4. Turso    (fallback3) — SQLite HTTP, 25M writes/month (resets 1st of month)

  Every write goes to ALL available backends simultaneously. Reads come from
  the highest-priority responsive backend. When a quota resets, the backend
  auto-restores and replays any missed records. Nothing is ever lost.

Used by:
  - context_bridge.py  (injects recent history into every AI prompt)
  - ai_handler.py      (persists every Telegram turn)
  - pipeline stages    (store key decisions)
  - /providers command (for memory status)

Spec Authority: v5.8 §2.10 (Mother Memory), §5.1–§5.3 (Telegram interface)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("factory.memory.mother_memory")

# ═══════════════════════════════════════════════════════════════════
# In-Memory Cache (fast local reads; survives within one process)
# ═══════════════════════════════════════════════════════════════════

_fallback_messages: list[dict] = []   # chronological, all operators
_fallback_insights: list[dict] = []   # long-term insights + decisions
_MAX_FALLBACK = 500


def _mirror_message(record: dict) -> None:
    _fallback_messages.append(record)
    if len(_fallback_messages) > _MAX_FALLBACK:
        _fallback_messages.pop(0)


def _mirror_insight(record: dict) -> None:
    _fallback_insights.append(record)
    if len(_fallback_insights) > 200:
        _fallback_insights.pop(0)


# ═══════════════════════════════════════════════════════════════════
# MemoryChain accessor (lazy init — safe to import at module level)
# ═══════════════════════════════════════════════════════════════════

_chain_initialized = False


async def _get_chain():
    global _chain_initialized
    from factory.memory.memory_chain import get_memory_chain
    chain = get_memory_chain()
    if not _chain_initialized:
        await chain.initialize()
        _chain_initialized = True
    return chain


# ═══════════════════════════════════════════════════════════════════
# Core Storage
# ═══════════════════════════════════════════════════════════════════

async def store_message(
    operator_id: str,
    role: str,                    # "user" | "assistant"
    content: str,
    intent: str = "",             # start_project, casual_chat, etc.
    project_id: Optional[str] = None,
    session_tag: str = "",        # optional grouping tag
) -> str:
    """Persist one Telegram message turn (both sides, including off-topic).

    Returns the message ID.
    """
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()

    record = {
        "id": msg_id,
        "operator_id": str(operator_id),
        "role": role,
        "content": content[:4000],  # cap to avoid bloat
        "intent": intent,
        "project_id": project_id or "",
        "session_tag": session_tag,
        "ts": ts,
    }

    # Mirror to local cache for ultra-fast reads within this process
    _mirror_message(record)

    # Persist to all backends via the chain (fan-out)
    try:
        chain = await _get_chain()
        ok = await chain.store_message(record)
        if ok:
            logger.debug(f"[mother-memory] stored {role} message {msg_id} → chain")
        else:
            logger.debug(f"[mother-memory] stored {role} message {msg_id} → cache only")
    except Exception as e:
        logger.debug(f"[mother-memory] chain store_message error: {e}")

    return msg_id


async def store_pipeline_decision(
    project_id: str,
    stage: str,
    decision_type: str,     # "stack_choice", "legal_framework", "arch_decision", etc.
    content: str,
    operator_id: str = "",
) -> str:
    """Store a key pipeline decision in Mother Memory for cross-session recall."""
    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()

    record = {
        "id": decision_id,
        "project_id": project_id,
        "stage": stage,
        "decision_type": decision_type,
        "content": content[:2000],
        "operator_id": operator_id,
        "ts": ts,
    }

    # Mirror to local cache
    _mirror_insight({**record, "type": "decision"})

    try:
        chain = await _get_chain()
        await chain.store_decision(record)
        logger.debug(f"[mother-memory] stored decision {decision_id} ({decision_type})")
    except Exception as e:
        logger.debug(f"[mother-memory] chain store_decision error: {e}")

    return decision_id


async def store_insight(
    operator_id: str,
    content: str,
    insight_type: str = "preference",  # preference | fact | lesson | error
    importance: int = 3,               # 1 (trivial) – 5 (critical)
    project_id: Optional[str] = None,
    tags: Optional[dict] = None,       # arbitrary key-value metadata (Issue 21)
) -> str:
    """Store a long-term insight (extracted from conversation or pipeline)."""
    insight_id = f"ins_{uuid.uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()

    record = {
        "id": insight_id,
        "operator_id": str(operator_id),
        "content": content[:1000],
        "insight_type": insight_type,
        "importance": importance,
        "project_id": project_id or "",
        "tags": tags or {},
        "ts": ts,
    }

    _mirror_insight({**record, "type": "insight"})

    try:
        chain = await _get_chain()
        await chain.store_insight(record)
    except Exception as e:
        logger.debug(f"[mother-memory] chain store_insight error: {e}")

    return insight_id


# ═══════════════════════════════════════════════════════════════════
# Structured-Node Store Helpers (Issue 21 §5a)
# ═══════════════════════════════════════════════════════════════════

async def store_requirement(
    project_id: str, operator_id: str,
    req_id: str, description: str, priority: str,
    acceptance_criteria: str, source_stage: str,
) -> None:
    """Store a product requirement node."""
    content = f"REQ:{req_id}|{priority}|{description[:400]}|AC:{acceptance_criteria[:200]}"
    await store_insight(
        operator_id=operator_id,
        project_id=project_id,
        content=content,
        insight_type="requirement",
        importance=8,
        tags={"source_stage": source_stage, "req_id": req_id},
    )


async def store_screen(
    project_id: str, operator_id: str,
    screen_id: str, name: str, purpose: str,
    components: list[str], api_bindings: list[str],
) -> None:
    """Store a UI screen node."""
    content = (
        f"SCREEN:{screen_id}|{name}|{purpose[:200]}"
        f"|components:{','.join(components[:10])}"
        f"|apis:{','.join(api_bindings[:10])}"
    )
    await store_insight(
        operator_id=operator_id,
        project_id=project_id,
        content=content,
        insight_type="screen",
        importance=7,
        tags={"screen_id": screen_id, "screen_name": name},
    )


async def store_api_endpoint(
    project_id: str, operator_id: str,
    path: str, method: str,
    request_schema: str, response_schema: str, auth: str,
) -> None:
    """Store an API endpoint node."""
    content = (
        f"API:{method.upper()} {path}"
        f"|req:{request_schema[:150]}|resp:{response_schema[:150]}|auth:{auth}"
    )
    await store_insight(
        operator_id=operator_id,
        project_id=project_id,
        content=content,
        insight_type="api_endpoint",
        importance=7,
        tags={"path": path, "method": method.upper()},
    )


async def store_data_model(
    project_id: str, operator_id: str,
    name: str, fields: str, relations: str,
) -> None:
    """Store a data model node."""
    content = f"MODEL:{name}|fields:{fields[:200]}|relations:{relations[:150]}"
    await store_insight(
        operator_id=operator_id,
        project_id=project_id,
        content=content,
        insight_type="data_model",
        importance=7,
        tags={"model_name": name},
    )


async def store_legal_clause(
    project_id: str, operator_id: str,
    doc: str, section: str, body: str, jurisdiction: str, citation: str,
) -> None:
    """Store a legal clause node."""
    content = f"LEGAL:{doc}|{section}|{jurisdiction}|{citation}|{body[:300]}"
    await store_insight(
        operator_id=operator_id,
        project_id=project_id,
        content=content,
        insight_type="legal_clause",
        importance=9,
        tags={"doc": doc, "jurisdiction": jurisdiction},
    )


async def store_source_file(
    project_id: str, operator_id: str,
    path: str, purpose: str, exported_symbols: list[str], sloc: int,
) -> None:
    """Store a generated source file reference node."""
    content = (
        f"FILE:{path}|{purpose[:150]}"
        f"|exports:{','.join(exported_symbols[:10])}"
        f"|sloc:{sloc}"
    )
    await store_insight(
        operator_id=operator_id,
        project_id=project_id,
        content=content,
        insight_type="source_file",
        importance=5,
        tags={"file_path": path, "sloc": str(sloc)},
    )


# ═══════════════════════════════════════════════════════════════════
# Retrieval
# ═══════════════════════════════════════════════════════════════════

async def get_conversation_history(
    operator_id: str,
    limit: int = 40,
) -> list[dict]:
    """Return the last N conversation turns for an operator.

    Tries the backend chain first (Neo4j → Supabase → Upstash → Turso);
    falls back to in-process cache if all backends are offline.

    Returns list of {"role": "user"|"assistant", "content": "..."} dicts
    in chronological order.
    """
    try:
        chain = await _get_chain()
        records = await chain.get_messages(operator_id, limit=limit)
        if records:
            return [{"role": r["role"], "content": r["content"]} for r in records]
    except Exception as e:
        logger.debug(f"[mother-memory] chain get_messages error: {e}")

    # In-process cache fallback
    records = [
        r for r in _fallback_messages
        if r.get("operator_id") == str(operator_id)
    ]
    records = records[-limit:]
    return [{"role": r["role"], "content": r["content"]} for r in records]


async def get_recent_insights(
    operator_id: str,
    limit: int = 8,
) -> list[dict]:
    """Return the most important insights/decisions for an operator."""
    try:
        chain = await _get_chain()
        records = await chain.get_insights(operator_id, limit=limit)
        if records:
            return records
    except Exception as e:
        logger.debug(f"[mother-memory] chain get_insights error: {e}")

    # In-process cache fallback
    records = [
        r for r in _fallback_insights
        if r.get("operator_id") == str(operator_id)
    ]
    records = sorted(records, key=lambda x: x.get("ts", ""), reverse=True)[:limit]
    return records


async def build_memory_block(
    operator_id: str,
    project_id: Optional[str] = None,
    history_limit: int = 20,
    insight_limit: int = 6,
) -> str:
    """Build a formatted memory block for injection into AI prompts.

    Includes:
    - Recent conversation (last 20 turns, including off-topic)
    - Key long-term insights about this operator
    """
    history = await get_conversation_history(operator_id, limit=history_limit)
    insights = await get_recent_insights(operator_id, limit=insight_limit)

    if not history and not insights:
        return ""

    lines: list[str] = ["╔══ OPERATOR MEMORY (persistent across sessions) ══"]

    # ── Long-term insights ──
    if insights:
        lines.append("│ Key facts about this operator:")
        for ins in insights:
            itype = ins.get("insight_type", ins.get("type", ""))
            content = ins.get("content", "")
            lines.append(f"│  [{itype}] {content[:120]}")

    # ── Recent conversation ──
    if history:
        lines.append("│")
        lines.append("│ Recent conversation history:")
        for turn in history:
            role_label = "Operator" if turn["role"] == "user" else "Bot"
            content = turn["content"].replace("\n", " ")[:200]
            lines.append(f"│  {role_label}: {content}")

    lines.append("╚══ END OPERATOR MEMORY ══\n")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Scout Result Cache (Exa quota conservation + cross-call reuse)
# ═══════════════════════════════════════════════════════════════════

# In-process Scout cache: query_hash → {source, result_preview, urls, ts}
_scout_cache: dict[str, dict] = {}
_MAX_SCOUT_CACHE = 200


async def store_scout_cache(
    query_hash: str,
    source: str,             # "exa", "exa_grounding/tavily", etc.
    query_preview: str,
    result_preview: str,     # truncated result for display
    urls: list[str],
    operator_id: str = "",
    project_id: Optional[str] = None,
) -> None:
    """Cache a Scout search result for reuse within the TTL window.

    Stored both in the fast in-process dict and in Mother Memory (insights).
    """
    import time
    entry = {
        "source": source,
        "query_preview": query_preview,
        "result_preview": result_preview[:800],
        "urls": urls[:10],
        "ts": time.time(),
    }

    # Fast in-process dict
    _scout_cache[query_hash] = entry
    if len(_scout_cache) > _MAX_SCOUT_CACHE:
        oldest = min(_scout_cache, key=lambda k: _scout_cache[k]["ts"])
        del _scout_cache[oldest]

    # Durable storage in Mother Memory insights
    content = f"SCOUT_CACHE:{query_hash}:{source}:{result_preview[:300]}"
    await store_insight(
        operator_id=operator_id or "system",
        content=content,
        insight_type="scout_cache",
        importance=2,
        project_id=project_id,
    )


async def get_cached_scout_result(
    query_hash: str,
    source: str = "",
    max_age_hours: int = 4,
) -> str | None:
    """Return a cached Scout result if it exists and is still fresh.

    Checks the fast in-process cache first, then Mother Memory insights.
    Returns the result_preview string or None if cache miss / expired.
    """
    import time
    max_age_seconds = max_age_hours * 3600

    # Fast path: in-process cache
    entry = _scout_cache.get(query_hash)
    if entry:
        age = time.time() - entry.get("ts", 0)
        if age < max_age_seconds:
            if not source or entry.get("source", "").startswith(source):
                logger.debug(
                    f"[scout-cache] HIT for hash={query_hash} "
                    f"(age={int(age)}s, source={entry.get('source')})"
                )
                return entry.get("result_preview", "")
        else:
            # Expired — evict
            del _scout_cache[query_hash]

    # Slow path: scan in-process insights cache
    prefix = f"SCOUT_CACHE:{query_hash}:"
    for record in reversed(_fallback_insights):
        content = record.get("content", "")
        if content.startswith(prefix):
            # Parse: SCOUT_CACHE:{hash}:{source}:{result_preview}
            parts = content.split(":", 3)
            if len(parts) >= 4:
                cached_source = parts[2]
                if not source or cached_source.startswith(source):
                    result = parts[3]
                    logger.debug(
                        f"[scout-cache] INSIGHT HIT for hash={query_hash}"
                    )
                    return result
    return None


# ═══════════════════════════════════════════════════════════════════
# Memory Chain Status (for /providers Telegram command)
# ═══════════════════════════════════════════════════════════════════

def get_memory_chain_status() -> list[dict]:
    """Return status of all memory backends (sync — does not await chain init)."""
    try:
        from factory.memory.memory_chain import get_memory_chain
        return get_memory_chain().status_report()
    except Exception:
        return []
