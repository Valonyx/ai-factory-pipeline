"""
AI Factory Pipeline v5.8 — Neo4j Integration (Mother Memory)

Implements:
  - §2.10 Mother Memory (knowledge graph)
  - §2.10.1 Schema (StackPattern, Component, DesignDNA, etc.)
  - §2.10.2 Janitor Agent (6-hour cycle)
  - FIX-27 HandoffDoc persistence
  - Time-travel node masking (PostSnapshot)

Spec Authority: v5.6 §2.10, §2.10.1, §2.10.2, FIX-27
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

logger = logging.getLogger("factory.integrations.neo4j")


# ═══════════════════════════════════════════════════════════════════
# Neo4j Node Types (§2.10.1)
# ═══════════════════════════════════════════════════════════════════

NODE_TYPES = {
    "StackPattern":       "Successful code patterns per stack",
    "Component":          "Individual components with success/failure counts",
    "DesignDNA":          "Color palettes, typography, layout patterns",
    "LegalDocTemplate":   "Legal document templates",
    "StorePolicyEvent":   "App Store / Play Store rejection history",
    "RegulatoryDecision": "KSA regulatory classification decisions",
    "Pattern":            "General patterns (architecture, error resolution)",
    "HandoffDoc":         "Operator handoff documentation (FIX-27, permanent)",
    "Graveyard":          "Archived dead data (via Janitor)",
    "PostSnapshot":       "Nodes hidden by time-travel restore",
    "WarRoomEvent":       "War Room session logs",
}

# Janitor-exempt node types
JANITOR_EXEMPT = {"HandoffDoc"}


# ═══════════════════════════════════════════════════════════════════
# Neo4j Client
# ═══════════════════════════════════════════════════════════════════


# Check driver availability once at import time (not per-query)
try:
    import neo4j as _neo4j_mod
    _NEO4J_AVAILABLE = True
except ImportError:
    _NEO4J_AVAILABLE = False


class Neo4jClient:
    """Neo4j client for Mother Memory knowledge graph.

    Spec: §2.10
    In production: uses neo4j Python driver with async sessions (pooled).
    Offline dev: in-memory graph stub.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "")
        self.password = password or os.getenv("NEO4J_PASSWORD", "")
        self._connected = bool(self.uri and self.password and _NEO4J_AVAILABLE)

        # Lazy driver singleton — created once, reused across queries
        self._driver = None

        # In-memory graph for offline dev
        self._nodes: dict[str, dict] = {}  # id -> node data
        self._relationships: list[dict] = []
        self._node_counter: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def _get_driver(self):
        """Return the shared async driver, creating it on first use."""
        if self._driver is None:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.uri, auth=("neo4j", self.password)
            )
        return self._driver

    # ═══════════════════════════════════════════════════════════════
    # Core Operations
    # ═══════════════════════════════════════════════════════════════

    async def run(
        self, query: str, params: Optional[dict] = None,
    ) -> list[dict]:
        """Execute a Cypher query.

        Spec: §2.10 (all Mother Memory operations)
        Production: uses neo4j AsyncGraphDatabase driver.
        Offline dev: logs query and returns empty results.
        """
        if not self._connected:
            logger.debug(f"[Neo4j offline] Query: {query[:100]}... params={params}")
            return []

        try:
            driver = await self._get_driver()
            async with driver.session() as session:
                result = await session.run(query, parameters=params or {})
                records = await result.data()
                return records
        except Exception as e:
            logger.warning(f"[Neo4j] Query failed: {e}")
            raise

    async def create_node(
        self, label: str, properties: dict,
    ) -> dict:
        """Create a node in the graph."""
        self._node_counter += 1
        node_id = properties.get("id", f"{label.lower()}_{self._node_counter}")
        node = {
            "id": node_id,
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **properties,
        }
        self._nodes[node_id] = node
        logger.debug(f"Created {label} node: {node_id}")
        return node

    async def create_relationship(
        self, from_id: str, rel_type: str, to_id: str,
        properties: Optional[dict] = None,
    ) -> dict:
        """Create a relationship between nodes."""
        rel = {
            "from": from_id,
            "type": rel_type,
            "to": to_id,
            "properties": properties or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._relationships.append(rel)
        return rel

    async def get_node(self, node_id: str) -> Optional[dict]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    async def find_nodes(
        self, label: str, filters: Optional[dict] = None,
    ) -> list[dict]:
        """Find nodes by label and optional filters."""
        results = []
        for node in self._nodes.values():
            if node.get("label") != label:
                continue
            if node.get("_hidden"):
                continue
            if filters:
                match = all(
                    node.get(k) == v for k, v in filters.items()
                )
                if not match:
                    continue
            results.append(node)
        return results

    # ═══════════════════════════════════════════════════════════════
    # Pattern Storage (§3.3 Mother Memory queries)
    # ═══════════════════════════════════════════════════════════════

    async def store_project_patterns(
        self, project_id: str, stack: str,
        screens: list, success: bool,
        war_room_count: int,
    ) -> None:
        """Store project patterns for cross-project learning.

        Spec: §2.10.1 (StackPattern nodes)
        """
        await self.create_node("StackPattern", {
            "id": f"sp_{project_id}",
            "project_id": project_id,
            "stack": stack,
            "screen_count": len(screens),
            "success": success,
            "war_room_count": war_room_count,
        })

    async def query_mother_memory(
        self, stack: str, screens: list[str],
        category: str = "",
    ) -> list[dict]:
        """Query Mother Memory for reusable patterns.

        Spec: §3.3 (Engineer queries before code generation)
        """
        patterns = await self.find_nodes("StackPattern", {"stack": stack})
        results = []
        for p in patterns:
            if not p.get("success"):
                continue
            if category and p.get("category") and p.get("category") != category:
                continue
            results.append({
                "project_id": p.get("project_id"),
                "stack": p.get("stack"),
                "screen_count": p.get("screen_count"),
                "success": p.get("success"),
                "category": p.get("category"),
            })
        return results

    # ═══════════════════════════════════════════════════════════════
    # FIX-27 Handoff Doc Persistence
    # ═══════════════════════════════════════════════════════════════

    async def store_handoff_docs(
        self, project_id: str, program_id: Optional[str],
        stack: str, app_category: str,
        docs: dict[str, str],
    ) -> int:
        """Store handoff docs as permanent HandoffDoc nodes.

        Spec: FIX-27, §2.10.1
        HandoffDoc nodes are Janitor-exempt (permanent=true).
        """
        stored = 0
        for doc_name, content in docs.items():
            if doc_name.startswith("_"):
                continue
            doc_type = doc_name.replace(".md", "").lower()
            await self.create_node("HandoffDoc", {
                "id": f"hd_{project_id}_{doc_name}",
                "project_id": project_id,
                "program_id": program_id,
                "stack": stack,
                "app_category": app_category,
                "doc_type": doc_type,
                "filename": doc_name,
                "content": content[:10000],
                "permanent": True,
            })
            await self.create_relationship(
                project_id, "HAS_HANDOFF_DOC",
                f"hd_{project_id}_{doc_type}",
                {"doc_type": doc_type},
            )
            stored += 1

        logger.info(
            f"[{project_id}] Stored {stored} HandoffDoc nodes (permanent)"
        )
        return stored

    # ═══════════════════════════════════════════════════════════════
    # Time-Travel: Node Masking
    # ═══════════════════════════════════════════════════════════════

    async def mask_post_snapshot_nodes(
        self, project_id: str, snapshot_time: str,
    ) -> int:
        """Hide nodes created after snapshot (time-travel restore).

        Spec: §2.9.2
        Sets _hidden=true, adds :PostSnapshot label.
        """
        masked = 0
        for node in self._nodes.values():
            if node.get("project_id") != project_id:
                continue
            if node.get("created_at", "") > snapshot_time:
                node["_hidden"] = True
                node["label"] = "PostSnapshot"
                masked += 1
        logger.info(f"[{project_id}] Masked {masked} post-snapshot nodes")
        return masked

    # ═══════════════════════════════════════════════════════════════
    # §2.10.2 Janitor Agent (6-Hour Cycle)
    # ═══════════════════════════════════════════════════════════════

    async def janitor_cycle(self) -> dict:
        """Run Janitor agent — archive rotting data.

        Spec: §2.10.2
        Categories: broken components, expired decisions,
        orphaned patterns, PostSnapshot orphans.
        HandoffDoc nodes are EXEMPT (permanent=true).
        """
        results = {"archived_count": 0, "categories": {}}
        now = datetime.now(timezone.utc)

        archived = 0
        for node_id, node in list(self._nodes.items()):
            label = node.get("label", "")

            # Never archive Janitor-exempt nodes
            if label in JANITOR_EXEMPT:
                continue

            created = node.get("created_at", "")
            if not created:
                continue

            try:
                created_dt = datetime.fromisoformat(created)
            except ValueError:
                continue

            age_days = (now - created_dt).days

            # Broken components: 0 successes, 2+ failures, >14 days
            if (label == "Component" and
                    node.get("success_count", 0) == 0 and
                    node.get("failure_count", 0) >= 2 and
                    age_days > 14):
                node["label"] = "Graveyard"
                node["archived_at"] = now.isoformat()
                node["archived_reason"] = "Broken: 0 successes, 2+ failures"
                archived += 1

            # Expired regulatory decisions: >6 months
            elif label == "RegulatoryDecision" and age_days > 180:
                node["label"] = "Graveyard"
                node["archived_at"] = now.isoformat()
                archived += 1

            # PostSnapshot orphans: >30 days
            elif label == "PostSnapshot" and node.get("_hidden") and age_days > 30:
                node["label"] = "Graveyard"
                node["archived_at"] = now.isoformat()
                archived += 1

        results["archived_count"] = archived
        logger.info(f"Janitor cycle: archived {archived} nodes")
        return results


# Singleton
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j() -> Neo4jClient:
    """Get or create Neo4j client singleton."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client


async def neo4j_run(query: str, params: Optional[dict] = None) -> list[dict]:
    """Convenience: execute Cypher query."""
    return await get_neo4j().run(query, params)

# Relationship types used in Mother Memory (§6.3)
RELATIONSHIP_TYPES: list[str] = [
    "USED_IN", "SOLVES", "SIMILAR_TO", "DEPENDS_ON",
    "TRIGGERS", "GENERATED_BY", "BELONGS_TO",
]


async def store_handoff_docs_in_memory(
    project_id: str,
    program_id: Optional[str],
    stack: str,
    app_category: str,
    docs: dict[str, str],
) -> int:
    """Store handoff docs in Mother Memory.

    Thin wrapper over Neo4jClient.store_handoff_docs with matching signature.
    Spec: FIX-27 (Handoff Intelligence Pack)
    """
    client = get_neo4j()
    try:
        return await client.store_handoff_docs(
            project_id=project_id,
            program_id=program_id,
            stack=stack,
            app_category=app_category,
            docs=docs,
        )
    except Exception as e:
        logger.warning(f"store_handoff_docs_in_memory failed: {e}")
        return 0


async def store_project_patterns(
    project_id: str,
    stack: str,
    screens: list,
    success: bool,
    war_room_count: int,
) -> int:
    """Module-level convenience for storing project patterns in Mother Memory.

    Spec: §6.3 Mother Memory
    """
    client = get_neo4j()
    try:
        await client.store_project_patterns(
            project_id=project_id,
            stack=stack,
            screens=screens,
            success=success,
            war_room_count=war_room_count,
        )
        return 1
    except Exception as e:
        logger.warning(f"store_project_patterns failed: {e}")
        return 0
