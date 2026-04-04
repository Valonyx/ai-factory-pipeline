"""
AI Factory Pipeline v5.6 — Janitor Agent

Implements:
  - §6.5 Janitor Agent Scheduling
  - Temp artifact cleanup (every 6 hours)
  - Snapshot pruning (1st of month)
  - Memory stats collection (every 24 hours)
  - Neo4j Graveyard management

Schedule (from §6.5):
  janitor_clean:   every 6 hours
  snapshot_prune:  1st of month
  memory_stats:    every 24 hours
  heartbeat_check: every 30 seconds (in-process, not here)

Run: python -m scripts.janitor [clean|prune|stats|all]

Spec Authority: v5.6 §6.5
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("factory.janitor")

# ═══════════════════════════════════════════════════════════════════
# §6.5 Schedule Constants
# ═══════════════════════════════════════════════════════════════════

JANITOR_SCHEDULE = {
    "janitor_clean": "every 6 hours",
    "snapshot_prune": "1st of month",
    "memory_stats": "every 24 hours",
    "heartbeat_check": "every 30 seconds (in-process)",
}

# Snapshot retention: keep last N per project
SNAPSHOT_RETENTION_COUNT = 50

# Graveyard threshold: components with 0% success after 5+ uses
GRAVEYARD_MIN_USES = 5
GRAVEYARD_MAX_SUCCESS_RATE = 0.1


# ═══════════════════════════════════════════════════════════════════
# Task 1: Temp Artifact Cleanup (every 6 hours)
# ═══════════════════════════════════════════════════════════════════


async def janitor_clean_artifacts(supabase_client=None) -> dict:
    """Delete expired temp artifacts from Supabase Storage.

    Spec: §7.5 [C3], §6.5
    """
    result = {"expired_found": 0, "deleted": 0, "errors": 0}

    if not supabase_client:
        logger.info("[DRY-RUN] janitor_clean_artifacts")
        return result

    now = datetime.now(timezone.utc).isoformat()

    try:
        expired = await supabase_client.table("temp_artifacts").select(
            "id, object_key, bucket",
        ).lt("expires_at", now).execute()

        result["expired_found"] = len(expired.data)

        for entry in expired.data:
            try:
                await supabase_client.storage.from_(
                    entry["bucket"],
                ).remove([entry["object_key"]])
                result["deleted"] += 1
            except Exception as e:
                result["errors"] += 1
                logger.error(f"Storage delete failed: {e}")

        if result["deleted"]:
            await supabase_client.table("temp_artifacts").delete().lt(
                "expires_at", now,
            ).execute()

    except Exception as e:
        logger.error(f"janitor_clean_artifacts failed: {e}")
        result["errors"] += 1

    logger.info(
        f"Janitor clean: {result['deleted']}/{result['expired_found']} "
        f"artifacts removed"
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Task 2: Snapshot Pruning (1st of month)
# ═══════════════════════════════════════════════════════════════════


async def janitor_prune_snapshots(supabase_client=None) -> dict:
    """Prune old snapshots, keeping last N per project.

    Spec: §6.5
    """
    result = {"projects_checked": 0, "snapshots_pruned": 0}

    if not supabase_client:
        logger.info("[DRY-RUN] janitor_prune_snapshots")
        return result

    try:
        projects = await supabase_client.table("state_snapshots").select(
            "project_id",
        ).execute()

        project_ids = set(r["project_id"] for r in projects.data)
        result["projects_checked"] = len(project_ids)

        for pid in project_ids:
            snaps = await supabase_client.table("state_snapshots").select(
                "id, snapshot_id",
            ).eq("project_id", pid).order(
                "snapshot_id", desc=True,
            ).execute()

            if len(snaps.data) > SNAPSHOT_RETENTION_COUNT:
                to_delete = snaps.data[SNAPSHOT_RETENTION_COUNT:]
                ids = [s["id"] for s in to_delete]
                for sid in ids:
                    await supabase_client.table(
                        "state_snapshots",
                    ).delete().eq("id", sid).execute()
                    result["snapshots_pruned"] += 1

    except Exception as e:
        logger.error(f"janitor_prune_snapshots failed: {e}")

    logger.info(
        f"Janitor prune: {result['snapshots_pruned']} snapshots removed "
        f"across {result['projects_checked']} projects"
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Task 3: Memory Stats Collection (every 24 hours)
# ═══════════════════════════════════════════════════════════════════


async def janitor_collect_memory_stats(
    neo4j_client=None,
    supabase_client=None,
) -> dict:
    """Collect and store Mother Memory statistics.

    Spec: §6.5
    """
    stats = {
        "node_counts": {},
        "graveyard_count": 0,
        "avg_component_success": 0.0,
        "error_pattern_count": 0,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    if not neo4j_client:
        logger.info("[DRY-RUN] janitor_collect_memory_stats")
        return stats

    try:
        # Count nodes by label
        node_types = [
            "Project", "Component", "ErrorPattern", "StackPattern",
            "DesignDNA", "RegulatoryDecision", "LegalDocTemplate",
            "Graveyard", "WarRoomEvent", "HandoffDoc", "StorePolicyEvent",
        ]
        for label in node_types:
            nodes = neo4j_client.find_nodes(label) if hasattr(
                neo4j_client, "find_nodes",
            ) else []
            stats["node_counts"][label] = len(nodes)

    except Exception as e:
        logger.error(f"Stats collection failed: {e}")

    # Store in Supabase
    if supabase_client:
        try:
            await supabase_client.table("memory_stats").insert({
                "stats": stats,
                "collected_at": stats["collected_at"],
            }).execute()
        except Exception as e:
            logger.error(f"Stats storage failed: {e}")

    logger.info(f"Memory stats: {stats['node_counts']}")
    return stats


# ═══════════════════════════════════════════════════════════════════
# Task 4: Graveyard Management
# ═══════════════════════════════════════════════════════════════════


async def janitor_update_graveyard(neo4j_client=None) -> dict:
    """Move low-performing components to Graveyard.

    Spec: §6.3 — Components with <10% success rate
    after 5+ uses get the :Graveyard label.
    """
    result = {"candidates_checked": 0, "graveyarded": 0}

    if not neo4j_client:
        logger.info("[DRY-RUN] janitor_update_graveyard")
        return result

    try:
        candidates = neo4j_client.query("""
            MATCH (c:Component)
            WHERE NOT c:Graveyard
              AND (c.success_count + c.failure_count) >= $min_uses
              AND toFloat(c.success_count)
                  / (c.success_count + c.failure_count) < $max_rate
            RETURN c.id AS id
        """, {
            "min_uses": GRAVEYARD_MIN_USES,
            "max_rate": GRAVEYARD_MAX_SUCCESS_RATE,
        })

        result["candidates_checked"] = len(candidates)

        for record in candidates:
            neo4j_client.query(
                "MATCH (c:Component {id: $id}) SET c:Graveyard",
                {"id": record["id"]},
            )
            result["graveyarded"] += 1

    except Exception as e:
        logger.error(f"Graveyard update failed: {e}")

    logger.info(
        f"Graveyard: {result['graveyarded']} components retired"
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Run All Tasks
# ═══════════════════════════════════════════════════════════════════


async def janitor_run_all(
    supabase_client=None,
    neo4j_client=None,
) -> dict:
    """Run all Janitor tasks."""
    logger.info("Janitor Agent — running all tasks")

    results = {
        "clean": await janitor_clean_artifacts(supabase_client),
        "prune": await janitor_prune_snapshots(supabase_client),
        "stats": await janitor_collect_memory_stats(
            neo4j_client, supabase_client,
        ),
        "graveyard": await janitor_update_graveyard(neo4j_client),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("Janitor Agent — all tasks complete")
    return results


# ═══════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    task = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"AI Factory Pipeline v5.6 — Janitor Agent ({task})")
    print("=" * 50)

    if task == "clean":
        asyncio.run(janitor_clean_artifacts())
    elif task == "prune":
        asyncio.run(janitor_prune_snapshots())
    elif task == "stats":
        asyncio.run(janitor_collect_memory_stats())
    elif task == "graveyard":
        asyncio.run(janitor_update_graveyard())
    elif task == "all":
        asyncio.run(janitor_run_all())
    else:
        print(f"Unknown task: {task}")
        print("Usage: python -m scripts.janitor [clean|prune|stats|graveyard|all]")