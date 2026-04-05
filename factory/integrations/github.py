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

import asyncio
import base64
import io
import json
import logging
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    from github import Github, GithubException
    _PYGITHUB_AVAILABLE = True
except ImportError:
    _PYGITHUB_AVAILABLE = False

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
        # PyGitHub client (None in offline/stub mode)
        self.client = None
        if _PYGITHUB_AVAILABLE and self.token:
            try:
                self.client = Github(self.token)
            except Exception:
                pass

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

    async def commit_files(
        self, repo: str, files: dict[str, str], message: str,
    ) -> dict:
        """Commit multiple files in a single operation.

        Spec: §2.9.1 (Write 3 — batch file commits)
        Returns: {"files": count, "shas": [...]}
        """
        shas = []
        for path, content in files.items():
            result = await self.commit_file(repo, path, content, message)
            shas.append(result["sha"])
        return {"files": len(files), "shas": shas}

    async def create_tag(
        self, repo: str, tag: str, message: str,
    ) -> dict:
        """Create a release tag on the latest commit.

        Spec: §4.9 S8 Handoff (release tagging)
        Returns: {"tag": tag, "target_sha": sha}
        """
        commits = self._commits.get(repo, [])
        target_sha = commits[-1]["sha"] if commits else f"sha-{self._commit_counter:06d}"
        logger.info(f"[{repo}] Created tag {tag} → {target_sha}")
        return {"tag": tag, "target_sha": target_sha, "message": message}

    # ═══════════════════════════════════════════════════════════════
    # §4.5.1 GitHub Actions CI/CD (NB4-01)
    # ═══════════════════════════════════════════════════════════════

    async def dispatch_workflow(
        self,
        repo_name: str,
        workflow_file: str,
        inputs: Dict[str, str],
        ref: str = "main",
    ) -> str:
        """Dispatch a GitHub Actions workflow and return the run ID.

        Spec: §4.5.1 CLI Build Paths
        Returns: workflow run ID string (for status polling)
        """
        if not self.client:
            raise RuntimeError("PyGitHub client not initialized — GITHUB_TOKEN required")

        repo = self.client.get_repo(repo_name)
        workflow = repo.get_workflow(workflow_file)

        success = workflow.create_dispatch(ref=ref, inputs=inputs)
        if not success:
            raise Exception(f"Failed to dispatch workflow {workflow_file}")

        logger.info(f"Dispatched workflow {workflow_file} on {repo_name}")

        # Brief wait for GitHub API to register the run
        await asyncio.sleep(3)

        runs = workflow.get_runs(event="workflow_dispatch")
        for run in runs:
            if run.status in ("queued", "in_progress"):
                return str(run.id)

        raise Exception("No active workflow run found after dispatch")

    async def poll_workflow_status(
        self,
        repo_name: str,
        run_id: str,
        timeout_minutes: int = 30,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Poll workflow run status until completion or timeout.

        Spec: §4.5.1 CLI Build Paths
        Returns: dict with status, conclusion, html_url
        """
        if not self.client:
            raise RuntimeError("PyGitHub client not initialized — GITHUB_TOKEN required")

        repo = self.client.get_repo(repo_name)
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60

        while True:
            if time.time() - start_time > timeout_seconds:
                raise TimeoutError(
                    f"Workflow run {run_id} did not complete within {timeout_minutes} minutes"
                )

            run = repo.get_workflow_run(int(run_id))
            logger.debug(f"Workflow run {run_id}: status={run.status}, conclusion={run.conclusion}")

            if run.status == "completed":
                return {
                    "run_id": run.id,
                    "status": run.status,
                    "conclusion": run.conclusion,
                    "html_url": run.html_url,
                    "created_at": run.created_at.isoformat(),
                    "updated_at": run.updated_at.isoformat(),
                }

            await asyncio.sleep(poll_interval)

    async def download_artifact(
        self,
        repo_name: str,
        artifact_name: str,
        destination_dir: Path,
        run_id: Optional[str] = None,
    ) -> List[Path]:
        """Download and extract a GitHub Actions artifact.

        Spec: §4.5.1 CLI Build Paths, Appendix D #6
        Returns: list of extracted file paths
        """
        if not self.client:
            raise RuntimeError("PyGitHub client not initialized — GITHUB_TOKEN required")

        repo = self.client.get_repo(repo_name)
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)

        if run_id:
            run = repo.get_workflow_run(int(run_id))
            artifacts = run.get_artifacts()
        else:
            artifacts = repo.get_artifacts()

        target_artifact = None
        for artifact in artifacts:
            if artifact.name == artifact_name:
                target_artifact = artifact
                break

        if not target_artifact:
            raise Exception(f"Artifact '{artifact_name}' not found")

        logger.info(
            f"Downloading artifact {artifact_name} "
            f"({target_artifact.size_in_bytes / 1_000_000:.1f} MB)"
        )

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"token {self.token}"}
            async with session.get(
                target_artifact.archive_download_url, headers=headers
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Artifact download failed: HTTP {resp.status}")
                zip_data = await resp.read()

        extracted_files: List[Path] = []
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for member in zf.namelist():
                zf.extract(member, destination_dir)
                extracted_files.append(destination_dir / member)

        logger.info(f"Extracted {len(extracted_files)} files to {destination_dir}")
        return extracted_files

    async def commit_workflow_template(
        self,
        repo_name: str,
        workflow_name: str,
        workflow_content: str,
    ) -> None:
        """Commit a GitHub Actions workflow file to .github/workflows/.

        Spec: §4.5.1 CLI Build Paths
        """
        if not self.client:
            raise RuntimeError("PyGitHub client not initialized — GITHUB_TOKEN required")

        workflow_path = f".github/workflows/{workflow_name}"
        repo = self.client.get_repo(repo_name)

        try:
            contents = repo.get_contents(workflow_path)
            repo.update_file(
                path=workflow_path,
                message=f"Update workflow {workflow_name}",
                content=workflow_content,
                sha=contents.sha,
            )
            logger.info(f"Updated workflow {workflow_path}")
        except Exception:
            repo.create_file(
                path=workflow_path,
                message=f"Add workflow {workflow_name}",
                content=workflow_content,
            )
            logger.info(f"Created workflow {workflow_path}")


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

async def commit_files(
    repo: str, files: dict[str, str], message: str,
) -> list[dict]:
    """Commit multiple files to a repository.

    Spec: §2.9.1 (Write 3 — batch file commits)
    Returns list of commit results.
    """
    client = get_github()
    results = []
    for path, content in files.items():
        result = await client.commit_file(repo, path, content, message)
        results.append(result)
    return results


async def create_release_tag(
    repo: str, tag: str, message: str, commit_sha: Optional[str] = None,
) -> dict:
    """Create a release tag on a repository.

    Spec: §4.9 S8 Handoff (release tagging)
    """
    client = get_github()
    client._commit_counter += 1
    return {"tag": tag, "repo": repo, "message": message, "sha": commit_sha or f"tag-{client._commit_counter:06d}"}
