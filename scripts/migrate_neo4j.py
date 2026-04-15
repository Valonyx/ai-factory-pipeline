"""
AI Factory Pipeline v5.8 — Neo4j Schema Migration

Implements:
  - §8.3.1 Neo4j Indexes and Constraints
  - 12 indexes across 8 node types
  - 1 uniqueness constraint (Project.id)
  - Additional indexes for FIX-27 HandoffDoc, WarRoomEvent, StorePolicyEvent

Idempotent — all CREATE use IF NOT EXISTS.
Run: python -m scripts.migrate_neo4j

Spec Authority: v5.8 §8.3.1
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("factory.migrate.neo4j")

# ═══════════════════════════════════════════════════════════════════
# §8.3.1 Neo4j Schema
# ═══════════════════════════════════════════════════════════════════

NEO4J_INDEXES = [
    # §6.3 Mother Memory v2 — 7 core node types
    "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.id)",
    "CREATE INDEX IF NOT EXISTS FOR (c:Component) ON (c.id)",
    "CREATE INDEX IF NOT EXISTS FOR (c:Component) ON (c.stack)",
    "CREATE INDEX IF NOT EXISTS FOR (ep:ErrorPattern) ON (ep.id)",
    "CREATE INDEX IF NOT EXISTS FOR (ep:ErrorPattern) ON (ep.stack)",
    "CREATE INDEX IF NOT EXISTS FOR (sp:StackPattern) ON (sp.id)",
    "CREATE INDEX IF NOT EXISTS FOR (sp:StackPattern) ON (sp.stack)",
    "CREATE INDEX IF NOT EXISTS FOR (d:DesignDNA) ON (d.id)",
    "CREATE INDEX IF NOT EXISTS FOR (d:DesignDNA) ON (d.category)",
    "CREATE INDEX IF NOT EXISTS FOR (rd:RegulatoryDecision) ON (rd.id)",
    "CREATE INDEX IF NOT EXISTS FOR (lt:LegalDocTemplate) ON (lt.id)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Graveyard) ON (g.id)",

    # Additional indexes for v5.8 extensions
    "CREATE INDEX IF NOT EXISTS FOR (we:WarRoomEvent) ON (we.project_id)",
    "CREATE INDEX IF NOT EXISTS FOR (we:WarRoomEvent) ON (we.resolved)",
    "CREATE INDEX IF NOT EXISTS FOR (pt:Pattern) ON (pt.pattern_type)",
    "CREATE INDEX IF NOT EXISTS FOR (hd:HandoffDoc) ON (hd.project_id)",
    "CREATE INDEX IF NOT EXISTS FOR (hd:HandoffDoc) ON (hd.doc_type)",
    "CREATE INDEX IF NOT EXISTS FOR (se:StorePolicyEvent) ON (se.platform)",
]

NEO4J_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
]


async def run_neo4j_migration(neo4j_client=None) -> dict:
    """Execute all Neo4j schema migrations.

    Returns: {"indexes_created": int, "constraints_created": int, "errors": []}
    """
    result = {"indexes_created": 0, "constraints_created": 0, "errors": []}

    if not neo4j_client:
        logger.info("No Neo4j client — running in dry-run mode")
        for cypher in NEO4J_INDEXES:
            label = cypher.split("(")[1].split(":")[1].split(")")[0]
            logger.info(f"  [DRY-RUN] Would create index on :{label}")
            result["indexes_created"] += 1
        for cypher in NEO4J_CONSTRAINTS:
            logger.info(f"  [DRY-RUN] Would create constraint")
            result["constraints_created"] += 1
        return result

    for cypher in NEO4J_INDEXES:
        try:
            neo4j_client.query(cypher)
            result["indexes_created"] += 1
        except Exception as e:
            result["errors"].append(str(e)[:200])

    for cypher in NEO4J_CONSTRAINTS:
        try:
            neo4j_client.query(cypher)
            result["constraints_created"] += 1
        except Exception as e:
            result["errors"].append(str(e)[:200])

    logger.info(
        f"Neo4j migration: {result['indexes_created']} indexes, "
        f"{result['constraints_created']} constraints"
    )
    return result


def get_neo4j_summary() -> dict:
    """Return summary of expected Neo4j schema."""
    return {
        "index_count": len(NEO4J_INDEXES),
        "constraint_count": len(NEO4J_CONSTRAINTS),
        "node_types": [
            "Project", "Component", "ErrorPattern", "StackPattern",
            "DesignDNA", "RegulatoryDecision", "LegalDocTemplate",
            "Graveyard", "WarRoomEvent", "Pattern", "HandoffDoc",
            "StorePolicyEvent",
        ],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("AI Factory Pipeline v5.8 — Neo4j Migration")
    print("=" * 50)
    result = asyncio.run(run_neo4j_migration())
    print(f"\nIndexes: {result['indexes_created']}")
    print(f"Constraints: {result['constraints_created']}")