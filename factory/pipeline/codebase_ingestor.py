"""
AI Factory Pipeline v5.8 — Codebase Ingestor (MODIFY Mode)

When pipeline_mode == MODIFY, the pipeline updates an existing app
instead of building from scratch. This module:

  1. Clones the existing repository from GitHub
  2. Analyzes the codebase structure (stack, architecture, patterns)
  3. Parses dependencies from manifest files
  4. Builds a context summary (max 150K tokens) for Claude
  5. Stores the analyzed context on PipelineState

Used by S0 (intake), S2 (blueprint), and S3 (codegen) in MODIFY mode.

Spec Authority: v5.6 §4.0 (NB4 Phase F, Part 20-21)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("factory.pipeline.codebase_ingestor")

# Max tokens to include from codebase (Claude's context window)
_MAX_CONTEXT_CHARS = 120_000   # ≈ 30K tokens
_MAX_FILE_CHARS    = 8_000     # per file
_SKIP_DIRS         = {".git", "node_modules", "__pycache__", ".gradle",
                      "build", "dist", ".dart_tool", "Pods", ".expo",
                      "android/.gradle", "ios/Pods", "coverage"}
_CODE_EXTENSIONS   = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".swift", ".kt", ".dart",
    ".yaml", ".yml", ".json", ".gradle", ".xml", ".html", ".css",
    ".md", ".toml", ".tf",
}
_MANIFEST_FILES = [
    "package.json", "pubspec.yaml", "requirements.txt", "setup.py",
    "Podfile", "build.gradle", "app/build.gradle", "pyproject.toml",
    "Gemfile", "Cargo.toml",
]


class CodebaseIngestor:
    """Clone and analyze an existing codebase for MODIFY mode."""

    def __init__(self, work_dir: Optional[str] = None) -> None:
        self._work_dir = work_dir or tempfile.mkdtemp(prefix="ai-factory-modify-")
        self._repo_path: Optional[Path] = None

    @property
    def repo_path(self) -> Optional[Path]:
        return self._repo_path

    # ── Clone ────────────────────────────────────────────────────────

    async def clone_repo(self, repo_url: str, branch: str = "main") -> Path:
        """Clone the repository to a temp directory.

        Accepts:
          • https://github.com/owner/repo
          • git@github.com:owner/repo.git
          • Local path (for testing)
        """
        dest = Path(self._work_dir) / "repo"
        if dest.exists():
            shutil.rmtree(dest)

        # Inject GitHub token if available
        token = os.getenv("GITHUB_TOKEN", "")
        if token and repo_url.startswith("https://github.com"):
            repo_url = repo_url.replace(
                "https://github.com",
                f"https://{token}@github.com",
            )

        logger.info(f"[codebase-ingestor] Cloning {repo_url} → {dest}")

        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", f"--branch={branch}", repo_url, str(dest),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            output = stdout.decode("utf-8", errors="replace")
            raise RuntimeError(f"git clone failed: {output[-500:]}")

        self._repo_path = dest
        logger.info(f"[codebase-ingestor] Cloned to {dest}")
        return dest

    # ── Stack Detection ──────────────────────────────────────────────

    def detect_stack(self, repo_path: Path) -> str:
        """Detect tech stack from project files."""
        if (repo_path / "pubspec.yaml").exists():
            return "flutterflow"
        if (repo_path / "package.json").exists():
            pkg = _read_json(repo_path / "package.json") or {}
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "expo" in deps or "react-native" in deps:
                return "react_native"
            return "react_native"   # generic RN
        if any((repo_path / p).exists() for p in ["App.xcodeproj", "App.xcworkspace"]):
            return "swift"
        if (repo_path / "app" / "build.gradle").exists():
            return "kotlin"
        if (repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists():
            return "python_backend"
        if (repo_path / "Assets").exists() or (repo_path / "ProjectSettings").exists():
            return "unity"
        return "unknown"

    def detect_architecture(self, repo_path: Path, stack: str) -> str:
        """Detect architecture pattern from file structure."""
        dirs = {d.name for d in repo_path.iterdir() if d.is_dir()}

        if "redux" in dirs or "store" in dirs:
            return "redux"
        if "viewmodels" in dirs or "ViewModels" in dirs:
            return "mvvm"
        if "controllers" in dirs or "Controllers" in dirs:
            return "mvc"
        if "blocs" in dirs or "bloc" in dirs:
            return "bloc"
        if "providers" in dirs:
            return "provider"
        if "routers" in dirs or "routes" in dirs:
            return "clean_architecture"
        return "unstructured"

    # ── Dependency Parsing ───────────────────────────────────────────

    def parse_dependencies(self, repo_path: Path) -> dict[str, list[str]]:
        """Parse dependencies from all known manifest files."""
        deps: dict[str, list[str]] = {}

        pkg_json = _read_json(repo_path / "package.json")
        if pkg_json:
            deps["npm"] = list({
                **pkg_json.get("dependencies", {}),
                **pkg_json.get("devDependencies", {}),
            }.keys())

        pubspec = _read_yaml(repo_path / "pubspec.yaml")
        if pubspec:
            d = pubspec.get("dependencies", {}) or {}
            deps["flutter"] = [k for k in d if k != "flutter"]

        req = _read_lines(repo_path / "requirements.txt")
        if req:
            deps["python"] = [r.split("==")[0].split(">=")[0].strip() for r in req if r.strip() and not r.startswith("#")]

        gradle = _read_text(repo_path / "app" / "build.gradle")
        if gradle:
            deps["gradle"] = re.findall(r"implementation ['\"]([^'\"]+)['\"]", gradle)

        return deps

    # ── File Tree Summary ────────────────────────────────────────────

    def summarize_structure(self, repo_path: Path) -> dict[str, Any]:
        """Walk the file tree and build a structural summary."""
        total_files = 0
        total_lines = 0
        by_extension: dict[str, int] = {}
        key_files: list[str] = []

        for path in repo_path.rglob("*"):
            if path.is_dir():
                continue
            # Skip irrelevant dirs
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            if path.suffix.lower() not in _CODE_EXTENSIONS:
                continue

            total_files += 1
            by_extension[path.suffix] = by_extension.get(path.suffix, 0) + 1
            try:
                content = path.read_text(errors="replace")
                total_lines += content.count("\n")
                rel = str(path.relative_to(repo_path))
                if any(kw in path.name.lower() for kw in
                       ["main", "app", "index", "router", "routes", "config", "types"]):
                    key_files.append(rel)
            except Exception:
                pass

        return {
            "total_files":  total_files,
            "total_lines":  total_lines,
            "by_extension": by_extension,
            "key_files":    key_files[:20],
        }

    # ── Context Extraction ───────────────────────────────────────────

    def extract_context(self, repo_path: Path, max_chars: int = _MAX_CONTEXT_CHARS) -> str:
        """Build a text context block for Claude from the most important files.

        Prioritises:
          1. Manifest files (package.json, pubspec.yaml, etc.)
          2. Entry points (main.*, App.*, index.*)
          3. Route/config files
          4. Sample screen/component files
        """
        parts: list[str] = []
        budget = max_chars

        def _add(path: Path, label: str) -> None:
            nonlocal budget
            if budget <= 0:
                return
            try:
                content = path.read_text(errors="replace")[:_MAX_FILE_CHARS]
                block = f"\n\n=== {label} ===\n{content}"
                if len(block) < budget:
                    parts.append(block)
                    budget -= len(block)
            except Exception:
                pass

        # 1. Manifests first
        for mf in _MANIFEST_FILES:
            p = repo_path / mf
            if p.exists():
                _add(p, mf)

        # 2. Entry points
        for pattern in ["main.*", "App.*", "index.*", "app.*"]:
            for p in sorted(repo_path.rglob(pattern))[:3]:
                if any(skip in p.parts for skip in _SKIP_DIRS):
                    continue
                _add(p, str(p.relative_to(repo_path)))

        # 3. Router/config files
        for pattern in ["*router*", "*routes*", "*config*", "*navigation*"]:
            for p in sorted(repo_path.rglob(pattern))[:2]:
                if any(skip in p.parts for skip in _SKIP_DIRS):
                    continue
                if p.suffix in _CODE_EXTENSIONS:
                    _add(p, str(p.relative_to(repo_path)))

        # 4. Sample screens/components
        for pattern in ["*screen*", "*page*", "*component*", "*widget*"]:
            for p in sorted(repo_path.rglob(pattern))[:3]:
                if any(skip in p.parts for skip in _SKIP_DIRS):
                    continue
                if p.suffix in _CODE_EXTENSIONS:
                    _add(p, str(p.relative_to(repo_path)))

        return "".join(parts)

    # ── Full Analysis ─────────────────────────────────────────────────

    async def analyze(self, repo_url: str, branch: str = "main") -> dict:
        """Full codebase analysis pipeline.

        Returns a dict suitable for storage on PipelineState.codebase_context.
        """
        repo_path = await self.clone_repo(repo_url, branch)
        stack        = self.detect_stack(repo_path)
        architecture = self.detect_architecture(repo_path, stack)
        dependencies = self.parse_dependencies(repo_path)
        structure    = self.summarize_structure(repo_path)
        context_text = self.extract_context(repo_path)

        return {
            "repo_url":     repo_url,
            "branch":       branch,
            "local_path":   str(repo_path),
            "stack":        stack,
            "architecture": architecture,
            "dependencies": dependencies,
            "structure":    structure,
            "context_text": context_text,   # Raw text for Claude
            "context_chars": len(context_text),
        }

    def cleanup(self) -> None:
        """Remove the temp clone directory."""
        try:
            shutil.rmtree(self._work_dir, ignore_errors=True)
        except Exception:
            pass


# ── File helpers ─────────────────────────────────────────────────────

def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(errors="replace") if path.exists() else None
    except Exception:
        return None


def _read_lines(path: Path) -> Optional[list[str]]:
    text = _read_text(path)
    return text.splitlines() if text else None


def _read_json(path: Path) -> Optional[dict]:
    import json
    text = _read_text(path)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_yaml(path: Path) -> Optional[dict]:
    text = _read_text(path)
    if not text:
        return None
    try:
        import yaml
        return yaml.safe_load(text)
    except Exception:
        return None
