"""
AI Factory Pipeline v5.8 — War Room Pattern Storage

Implements:
  - §2.2.4 War Room resolution logging to Neo4j
  - §2.10.1 WarRoomEvent node type
  - Cross-project learning from fix patterns
  - Pattern querying for future similar errors

Spec Authority: v5.8 §2.2.4, §2.10.1
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import PipelineState
from factory.war_room.levels import FixResult, WarRoomLevel

logger = logging.getLogger("factory.war_room.patterns")


# ═══════════════════════════════════════════════════════════════════
# Pattern Storage (Mother Memory)
# ═══════════════════════════════════════════════════════════════════


async def store_war_room_event(
    state: PipelineState,
    result: FixResult,
    neo4j_client=None,
) -> Optional[str]:
    """Store War Room resolution as WarRoomEvent in Mother Memory.

    Spec: §2.10.1 WarRoomEvent node type

    All War Room sessions are logged for cross-project learning.
    """
    if not neo4j_client:
        try:
            from factory.integrations.neo4j import get_neo4j
            neo4j_client = get_neo4j()
        except ImportError:
            logger.debug("Neo4j not available for pattern storage")
            return None

    properties = {
        "project_id": state.project_id,
        "stage": state.current_stage.value,
        "stack": getattr(state, "selected_stack", "unknown"),
        "level": result.level.value,
        "level_name": result.level.name,
        "resolved": result.resolved,
        "error_summary": result.error_summary[:500],
        "fix_applied": result.fix_applied[:1000],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if result.research:
        properties["research_summary"] = result.research[:1000]

    if result.plan:
        properties["root_cause"] = result.plan.get("root_cause", "")
        properties["cleanup_commands_count"] = len(
            result.plan.get("cleanup_commands", [])
        )
        properties["rewrite_files_count"] = len(
            result.plan.get("rewrite_plan", [])
        )
    node = await neo4j_client.create_node("WarRoomEvent", properties)
    node_id = node.get("id") if isinstance(node, dict) else None

    logger.info(
        f"[{state.project_id}] War Room event stored: "
        f"L{result.level.value} {'✅' if result.resolved else '❌'} "
        f"→ node {node_id}"
    )
    return node_id


async def query_similar_errors(
    error_message: str,
    stack: str = "",
    neo4j_client=None,
    limit: int = 5,
) -> list[dict]:
    """Query Mother Memory for similar past War Room resolutions.

    Spec: §2.10.1

    Used before escalation to check if a similar error was resolved
    in a previous project.
    """
    if not neo4j_client:
        try:
            from factory.integrations.neo4j import get_neo4j
            neo4j_client = get_neo4j()
        except ImportError:
            return []

    # Find resolved WarRoomEvent nodes
    filters = {"resolved": True}
    if stack:
        filters["stack"] = stack

    events = await neo4j_client.find_nodes("WarRoomEvent", filters)
    # Simple keyword matching (production would use vector similarity)
    error_words = set(error_message.lower().split())
    scored: list[tuple[float, dict]] = []

    for event in events:
        event_words = set(
            event.get("error_summary", "").lower().split()
        )
        if not event_words:
            continue
        overlap = len(error_words & event_words)
        score = overlap / max(len(error_words), 1)
        if score > 0.2:
            scored.append((score, event))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = [
        {
            "score": round(s, 3),
            "level": e.get("level"),
            "error_summary": e.get("error_summary", ""),
            "fix_applied": e.get("fix_applied", ""),
            "root_cause": e.get("root_cause", ""),
            "project_id": e.get("project_id", ""),
        }
        for s, e in scored[:limit]
    ]

    if results:
        logger.info(
            f"Found {len(results)} similar War Room resolutions"
        )

    return results


async def store_fix_pattern(
    state: PipelineState,
    error_type: str,
    fix_description: str,
    success: bool,
    neo4j_client=None,
) -> Optional[str]:
    """Store a successful fix as a reusable Pattern in Mother Memory.

    Spec: §2.10.1 Pattern node type

    Stored patterns are queried by Engineer before code generation
    to avoid known pitfalls.
    """
    if not success:
        return None

    if not neo4j_client:
        try:
            from factory.integrations.neo4j import get_neo4j
            neo4j_client = get_neo4j()
        except ImportError:
            return None

    properties = {
        "pattern_type": "error_resolution",
        "error_type": error_type,
        "fix_description": fix_description[:2000],
        "project_id": state.project_id,
        "stack": getattr(state, "selected_stack", "unknown"),
        "success_count": 1,
        "failure_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    node = await neo4j_client.create_node("WarRoomEvent", properties)
    node_id = node.get("id") if isinstance(node, dict) else None

    logger.info(
        f"[{state.project_id}] Fix pattern stored: "
        f"{error_type} → node {node_id}"
    )
    return node_id