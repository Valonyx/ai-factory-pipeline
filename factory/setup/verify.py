"""
AI Factory Pipeline v5.8 — Service Connection Verifiers

Implements the 5 service verification checks from the setup wizard (§7.1.2):
  1. verify_anthropic()  — Claude API ping
  2. verify_perplexity() — Perplexity API ping
  3. verify_supabase()   — Supabase table query
  4. verify_neo4j()      — Cypher RETURN 1
  5. verify_github()     — GitHub rate_limit endpoint

Each verifier:
  - Uses get_secret() for credentials (§2.11)
  - Returns dict with status, latency_ms, and detail
  - Raises on failure (caught by wizard)
  - Respects 10s timeout for network calls

Spec Authority: v5.8 §7.1.2
"""

from __future__ import annotations

import logging
import time
from typing import Any

from factory.core.secrets import get_secret

logger = logging.getLogger("factory.setup.verify")

# Timeout for all verification requests (seconds)
_VERIFY_TIMEOUT: float = 10.0


async def verify_anthropic() -> dict[str, Any]:
    """Verify Anthropic API connection.

    Spec: §7.1.2 — verify_anthropic()
    Sends a minimal models list request to confirm API key validity.
    """
    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    start = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            latency = (time.monotonic() - start) * 1000

            if resp.status_code == 200:
                return {
                    "service": "Anthropic",
                    "status": "connected",
                    "latency_ms": round(latency, 1),
                    "detail": "API key valid",
                }
            else:
                raise ConnectionError(
                    f"Anthropic API returned {resp.status_code}"
                )
    except ImportError:
        raise EnvironmentError(
            "httpx not installed — required for service verification"
        )


async def verify_perplexity() -> dict[str, Any]:
    """Verify Perplexity API connection.

    Spec: §7.1.2 — verify_perplexity()
    Sends a minimal chat completion to confirm API key validity.
    Uses sonar (cheapest model) with max_tokens=1 to minimize cost.
    """
    api_key = get_secret("PERPLEXITY_API_KEY")
    if not api_key:
        raise EnvironmentError("PERPLEXITY_API_KEY not set")

    start = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            latency = (time.monotonic() - start) * 1000

            if resp.status_code == 200:
                return {
                    "service": "Perplexity",
                    "status": "connected",
                    "latency_ms": round(latency, 1),
                    "detail": "API key valid (sonar ping)",
                }
            else:
                raise ConnectionError(
                    f"Perplexity API returned {resp.status_code}"
                )
    except ImportError:
        raise EnvironmentError("httpx not installed")


async def verify_supabase() -> dict[str, Any]:
    """Verify Supabase connection.

    Spec: §7.1.2 — verify_supabase()
    Attempts a lightweight table query to confirm URL + service key.
    """
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")

    start = time.monotonic()
    try:
        from supabase import create_client
        client = create_client(url, key)
        # Lightweight health query — empty data or 404 still proves connection
        client.table("operator_whitelist").select("count").limit(1).execute()
        latency = (time.monotonic() - start) * 1000
        return {
            "service": "Supabase",
            "status": "connected",
            "latency_ms": round(latency, 1),
            "detail": f"Connected to {url[:40]}...",
        }
    except ImportError:
        raise EnvironmentError("supabase not installed")
    except Exception as e:
        # "relation does not exist" still proves the connection works
        error_str = str(e).lower()
        if "does not exist" in error_str or "relation" in error_str:
            latency = (time.monotonic() - start) * 1000
            return {
                "service": "Supabase",
                "status": "connected",
                "latency_ms": round(latency, 1),
                "detail": "Connected (tables not yet created)",
            }
        raise


async def verify_neo4j() -> dict[str, Any]:
    """Verify Neo4j connection.

    Spec: §7.1.2 — verify_neo4j()
    Sends RETURN 1 AS ok to confirm connection credentials.
    """
    uri = get_secret("NEO4J_URI")
    password = get_secret("NEO4J_PASSWORD")
    if not uri or not password:
        raise EnvironmentError("NEO4J_URI or NEO4J_PASSWORD not set")

    start = time.monotonic()
    try:
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            uri, auth=("neo4j", password)
        )
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            assert record["ok"] == 1
        await driver.close()

        latency = (time.monotonic() - start) * 1000
        return {
            "service": "Neo4j",
            "status": "connected",
            "latency_ms": round(latency, 1),
            "detail": f"Connected to {uri[:40]}...",
        }
    except ImportError:
        raise EnvironmentError("neo4j not installed")


async def verify_github() -> dict[str, Any]:
    """Verify GitHub API connection.

    Spec: §7.1.2 — verify_github()
    Hits /rate_limit endpoint to confirm token validity.
    """
    token = get_secret("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN not set")

    start = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT) as client:
            resp = await client.get(
                "https://api.github.com/rate_limit",
                headers={"Authorization": f"token {token}"},
            )
            latency = (time.monotonic() - start) * 1000

            if resp.status_code == 200:
                data = resp.json()
                remaining = data.get("rate", {}).get("remaining", "?")
                return {
                    "service": "GitHub",
                    "status": "connected",
                    "latency_ms": round(latency, 1),
                    "detail": f"Token valid ({remaining} requests remaining)",
                }
            else:
                raise ConnectionError(
                    f"GitHub API returned {resp.status_code}"
                )
    except ImportError:
        raise EnvironmentError("httpx not installed")


# ═══════════════════════════════════════════════════════════════════
# Convenience: run all verifiers
# ═══════════════════════════════════════════════════════════════════

async def verify_all_services() -> dict[str, dict]:
    """Run all 5 service verifiers and collect results.

    Spec: §7.1.2

    Returns:
        {service_name: {"status": str, "latency_ms": float, "detail": str}}
    """
    verifiers = [
        ("Anthropic", verify_anthropic),
        ("Perplexity", verify_perplexity),
        ("Supabase", verify_supabase),
        ("Neo4j", verify_neo4j),
        ("GitHub", verify_github),
    ]

    results = {}
    for name, fn in verifiers:
        try:
            result = await fn()
            results[name] = result
        except Exception as e:
            results[name] = {
                "service": name,
                "status": "failed",
                "latency_ms": 0,
                "detail": str(e)[:200],
            }
            logger.warning(f"Verification failed for {name}: {e}")

    passed = sum(1 for r in results.values() if r["status"] == "connected")
    logger.info(f"Service verification: {passed}/{len(verifiers)} connected")

    return results
