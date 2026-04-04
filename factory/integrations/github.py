"""
AI Factory Pipeline v5.6 — GitHub Integration

Implements:
  - §2.9.1 Write 3 of triple-write (versioned state commits)
  - §4.7.3 Binary commits (icons, build artifacts)
  - §2.9.2 Reset to commit (time-travel restore)
  - Repo creation and management

Spec Authority: v5.6 §2.9, §4.7.3
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("factory.integrations.github")


# ═══════════════════════════════════════════════════════════════════
# GitHub Client
# ═══════════════════════════════════════════════════════════════════


class GitHubClient:
    """GitHub API client for pipeline repository operations.

    Spec: §2.9.1 (Write 3), §4.7.3 (binary commits)
    In production: uses PyGithub or httpx against GitHub REST API.
    Current implementation: interface-compatible stub for offline dev.
    """

    API_BASE = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self._connected = bool(self.token)
        # In-memory store for offline dev
        self._repos: dict[str, dict[str, str]] = {}
        self._commits: dict[str, list[dict]] = {}
        self._commit_counter: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ═══════════════════════════════════════════════════════════════
    # File Operations
    # ═══════════════════════════════════════════════════════════════

    async def commit_file(
        self, repo: str, path: str, content: str, message: str,
    ) -> dict:
        """Commit a text file to repository.

        Spec: §2.9.1 (Write 3 — state snapshots)
        Returns: {"sha": commit_sha, "path": path}
        """
        self._commit_counter += 1
        sha = f"sha-{self._commit_counter:06d}-{hash(content) % 10000:04d}"

        if repo not in self._repos:
            self._repos[repo] = {}
        self._repos[repo][path] = content

        if repo not in self._commits:
            self._commits[repo] = []
        commit = {
            "sha": sha,
            "path": path,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._commits[repo].append(commit)

        logger.debug(f"[{repo}] Committed {path}: {sha}")
        return {"sha": sha, "path": path}

    async def commit_binary(
        self, repo: str, path: str, content: bytes, message: str,
    ) -> dict:
        """Commit a binary file (icons, build artifacts).

        Spec: §4.7.3 (platform icon generation)
        """
        self._commit_counter += 1
        sha = f"bin-{self._commit_counter:06d}"

        if repo not in self._repos:
            self._repos[repo] = {}
        self._repos[repo][path] = f"<binary:{len(content)} bytes>"

        if repo not in self._commits:
            self._commits[repo] = []
        self._commits[repo].append({
            "sha": sha, "path": path, "message": message,
            "binary": True, "size": len(content),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.debug(f"[{repo}] Binary commit {path}: {sha} ({len(content)} bytes)")
        return {"sha": sha, "path": path}

    async def get_file(self, repo: str, path: str) -> Optional[str]:
        """Read a file from repository."""
        return self._repos.get(repo, {}).get(path)

    async def list_files(self, repo: str) -> list[str]:
        """List all files in repository."""
        return list(self._repos.get(repo, {}).keys())

    # ═══════════════════════════════════════════════════════════════
    # Repository Operations
    # ═══════════════════════════════════════════════════════════════

    async def create_repo(self, repo_name: str, private: bool = True) -> dict:
        """Create a new repository."""
        self._repos[repo_name] = {}
        self._commits[repo_name] = []
        logger.info(f"Created repo: {repo_name} (private={private})")
        return {"name": repo_name, "private": private}

    async def repo_exists(self, repo_name: str) -> bool:
        """Check if repository exists."""
        return repo_name in self._repos

    # ═══════════════════════════════════════════════════════════════
    # §2.9.2 Time-Travel: Reset to Commit
    # ═══════════════════════════════════════════════════════════════

    async def reset_to_commit(self, repo: str, commit_sha: str) -> dict:
        """Reset repository to a specific commit (time-travel restore).

        Spec: §2.9.2
        In production: git reset --hard to snapshot commit SHA.
        """
        commits = self._commits.get(repo, [])
        target_idx = None
        for i, c in enumerate(commits):
            if c["sha"] == commit_sha:
                target_idx = i
                break

        if target_idx is None:
            logger.warning(f"[{repo}] Commit {commit_sha} not found for reset")
            return {"success": False, "error": "Commit not found"}

        # Truncate commits after target
        self._commits[repo] = commits[:target_idx + 1]
        logger.info(f"[{repo}] Reset to commit {commit_sha}")
        return {"success": True, "commit_sha": commit_sha}

    # ═══════════════════════════════════════════════════════════════
    # Commit History
    # ═══════════════════════════════════════════════════════════════

    async def get_commits(
        self, repo: str, limit: int = 10,
    ) -> list[dict]:
        """Get recent commits for a repository."""
        commits = self._commits.get(repo, [])
        return commits[-limit:]


# Convenience functions (module-level)

_github_client: Optional[GitHubClient] = None


def get_github() -> GitHubClient:
    """Get or create GitHub client singleton."""
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client


async def github_commit_file(
    repo: str, path: str, content: str, message: str,
) -> dict:
    """Convenience: commit a file."""
    return await get_github().commit_file(repo, path, content, message)


async def github_commit_binary(
    repo: str, path: str, content: bytes, message: str,
) -> dict:
    """Convenience: commit a binary file."""
    return await get_github().commit_binary(repo, path, content, message)


async def github_reset_to_commit(repo: str, commit_sha: str) -> dict:
    """Convenience: reset repo to commit."""
    return await get_github().reset_to_commit(repo, commit_sha)