"""
AI Factory Pipeline v5.8 — Neo4j Memory Backend (Primary)

Wraps the existing Neo4j client (factory/integrations/neo4j.py) as a
MemoryBackend. Neo4j is the highest-priority backend in the chain.

Free tier (AuraDB Free):
  200K nodes, 400K relationships, 200MB storage
  No daily/hourly rate limit — only storage cap
  Connection: neo4j+s://3d7d8c68.databases.neo4j.io

The backend marks itself unavailable if Neo4j is unreachable or returns
storage-full errors. It auto-recovers when connectivity is restored.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from factory.memory.backends.base import MemoryBackend

logger = logging.getLogger("factory.memory.backends.neo4j")


class Neo4jMemoryBackend(MemoryBackend):
    name = "neo4j"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from factory.integrations.neo4j import get_neo4j
            self._client = get_neo4j()
        return self._client

    async def ping(self) -> bool:
        try:
            client = self._get_client()
            if not client.is_connected:
                return False
            result = await client.run("RETURN 1 AS ok", {})
            return bool(result)
        except Exception as e:
            logger.debug(f"[neo4j] ping failed: {e}")
            return False

    async def setup(self) -> bool:
        """Create indexes for fast operator_id lookups."""
        try:
            client = self._get_client()
            if not client.is_connected:
                return False
            await client.run(
                "CREATE INDEX msg_op_idx IF NOT EXISTS "
                "FOR (m:OperatorMessage) ON (m.operator_id)",
                {},
            )
            await client.run(
                "CREATE INDEX insight_op_idx IF NOT EXISTS "
                "FOR (i:MemoryInsight) ON (i.operator_id)",
                {},
            )
            return True
        except Exception as e:
            logger.debug(f"[neo4j] setup failed: {e}")
            return False

    async def store_message(self, record: dict) -> bool:
        try:
            client = self._get_client()
            if not client.is_connected:
                return False
            await client.run(
                """
                MERGE (op:Operator {id: $operator_id})
                CREATE (m:OperatorMessage {
                    id: $id, operator_id: $operator_id, role: $role,
                    content: $content, intent: $intent,
                    project_id: $project_id, session_tag: $session_tag, ts: $ts
                })
                CREATE (op)-[:SAID]->(m)
                """,
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[neo4j] store_message failed: {e}")
            raise

    async def get_messages(self, operator_id: str, limit: int = 40) -> list[dict]:
        try:
            client = self._get_client()
            if not client.is_connected:
                return []
            rows = await client.run(
                """
                MATCH (m:OperatorMessage {operator_id: $operator_id})
                RETURN m.role AS role, m.content AS content, m.ts AS ts,
                       m.intent AS intent, m.project_id AS project_id
                ORDER BY m.ts DESC LIMIT $limit
                """,
                {"operator_id": operator_id, "limit": limit},
            )
            return list(reversed(rows))
        except Exception as e:
            logger.debug(f"[neo4j] get_messages failed: {e}")
            return []

    async def store_decision(self, record: dict) -> bool:
        try:
            client = self._get_client()
            if not client.is_connected:
                return False
            await client.run(
                """
                MERGE (p:Project {id: $project_id})
                CREATE (d:PipelineDecision {
                    id: $id, project_id: $project_id, stage: $stage,
                    decision_type: $decision_type, content: $content,
                    operator_id: $operator_id, ts: $ts
                })
                CREATE (p)-[:HAS_DECISION]->(d)
                """,
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[neo4j] store_decision failed: {e}")
            raise

    async def store_insight(self, record: dict) -> bool:
        try:
            client = self._get_client()
            if not client.is_connected:
                return False
            await client.run(
                """
                MERGE (op:Operator {id: $operator_id})
                CREATE (i:MemoryInsight {
                    id: $id, operator_id: $operator_id, content: $content,
                    insight_type: $insight_type, importance: $importance,
                    project_id: $project_id, ts: $ts
                })
                CREATE (op)-[:HAS_INSIGHT]->(i)
                """,
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[neo4j] store_insight failed: {e}")
            raise

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        try:
            client = self._get_client()
            if not client.is_connected:
                return []
            return await client.run(
                """
                MATCH (i:MemoryInsight {operator_id: $operator_id})
                RETURN i.content AS content, i.insight_type AS insight_type,
                       i.importance AS importance, i.ts AS ts
                ORDER BY i.importance DESC, i.ts DESC LIMIT $limit
                """,
                {"operator_id": operator_id, "limit": limit},
            )
        except Exception as e:
            logger.debug(f"[neo4j] get_insights failed: {e}")
            return []

    async def get_messages_since(self, operator_id: str, since_ts: str) -> list[dict]:
        try:
            client = self._get_client()
            if not client.is_connected:
                return []
            rows = await client.run(
                """
                MATCH (m:OperatorMessage {operator_id: $operator_id})
                WHERE m.ts > $since_ts
                RETURN m.id AS id, m.role AS role, m.content AS content,
                       m.ts AS ts, m.intent AS intent,
                       m.project_id AS project_id, m.session_tag AS session_tag
                ORDER BY m.ts ASC
                """,
                {"operator_id": operator_id, "since_ts": since_ts},
            )
            return rows
        except Exception:
            return []
