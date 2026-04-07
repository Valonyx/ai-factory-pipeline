"""
AI Factory Pipeline v5.6 — Version Manager

Manages semantic versioning for generated and modified apps:
  • Read current version from project manifests
  • Increment (major/minor/patch) with commit tracking
  • Update version numbers across all platform files
  • Generate changelogs
  • Tag git releases

Spec Authority: v5.6 §4.0 (NB4 Part 23)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("factory.versioning.version_manager")


@dataclass
class Version:
    major: int
    minor: int
    patch: int
    build: int = 0    # Platform build number (auto-incremented)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def semver(self) -> str:
        return str(self)

    def bump_major(self) -> "Version":
        return Version(self.major + 1, 0, 0, self.build + 1)

    def bump_minor(self) -> "Version":
        return Version(self.major, self.minor + 1, 0, self.build + 1)

    def bump_patch(self) -> "Version":
        return Version(self.major, self.minor, self.patch + 1, self.build + 1)

    def bump(self, bump_type: str = "patch") -> "Version":
        if bump_type == "major":
            return self.bump_major()
        if bump_type == "minor":
            return self.bump_minor()
        return self.bump_patch()

    @classmethod
    def parse(cls, version_str: str) -> "Version":
        """Parse 'X.Y.Z' or 'X.Y.Z+B' into Version."""
        m = re.match(r"(\d+)\.(\d+)\.(\d+)(?:\+(\d+))?", version_str.strip())
        if not m:
            return cls(1, 0, 0)
        return cls(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)) if m.group(4) else 0,
        )

    @classmethod
    def initial(cls) -> "Version":
        return cls(1, 0, 0, 1)


class VersionManager:
    """Read, bump, and write version numbers across platform manifests."""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    # ── Read Current Version ─────────────────────────────────────────

    def get_current_version(self) -> Version:
        """Detect and return current version from manifest files."""
        # pubspec.yaml (Flutter)
        pubspec = self.repo_path / "pubspec.yaml"
        if pubspec.exists():
            text = pubspec.read_text(errors="replace")
            m = re.search(r"^version:\s+(.+)$", text, re.MULTILINE)
            if m:
                return Version.parse(m.group(1))

        # package.json (React Native / JS)
        pkg = self.repo_path / "package.json"
        if pkg.exists():
            import json
            try:
                data = json.loads(pkg.read_text())
                if v := data.get("version"):
                    return Version.parse(v)
            except Exception:
                pass

        # app/build.gradle (Kotlin/Android)
        gradle = self.repo_path / "app" / "build.gradle"
        if gradle.exists():
            text = gradle.read_text(errors="replace")
            m = re.search(r'versionName\s+"([^"]+)"', text)
            if m:
                return Version.parse(m.group(1))

        # Info.plist (Swift/iOS)
        plist = self.repo_path / "Info.plist"
        if plist.exists():
            text = plist.read_text(errors="replace")
            m = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", text)
            if m:
                return Version.parse(m.group(1))

        return Version.initial()

    # ── Update Version ───────────────────────────────────────────────

    def update_version_files(self, new_version: Version) -> list[str]:
        """Update version in all detected manifest files.

        Returns list of files updated.
        """
        updated: list[str] = []

        # pubspec.yaml
        pubspec = self.repo_path / "pubspec.yaml"
        if pubspec.exists():
            text = pubspec.read_text(errors="replace")
            new_text = re.sub(
                r"^(version:\s+)(.+)$",
                f"\\g<1>{new_version}+{new_version.build}",
                text, flags=re.MULTILINE,
            )
            if new_text != text:
                pubspec.write_text(new_text)
                updated.append("pubspec.yaml")

        # package.json
        pkg = self.repo_path / "package.json"
        if pkg.exists():
            import json
            try:
                data = json.loads(pkg.read_text())
                data["version"] = str(new_version)
                pkg.write_text(json.dumps(data, indent=2) + "\n")
                updated.append("package.json")
            except Exception:
                pass

        # app/build.gradle
        gradle = self.repo_path / "app" / "build.gradle"
        if gradle.exists():
            text = gradle.read_text(errors="replace")
            new_text = re.sub(
                r'versionName\s+"[^"]+"',
                f'versionName "{new_version}"',
                text,
            )
            new_text = re.sub(
                r"versionCode\s+\d+",
                f"versionCode {new_version.build}",
                new_text,
            )
            if new_text != text:
                gradle.write_text(new_text)
                updated.append("app/build.gradle")

        return updated

    # ── Changelog Generation ─────────────────────────────────────────

    def generate_changelog(
        self,
        old_version: Version,
        new_version: Version,
        changes: list[str],
    ) -> str:
        """Generate a changelog entry for this version bump."""
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        lines = [
            f"## [{new_version}] — {date}",
            "",
            f"### Changes from {old_version}",
            "",
        ]
        for change in changes:
            lines.append(f"- {change}")
        lines.append("")

        return "\n".join(lines)

    def prepend_changelog(self, entry: str) -> bool:
        """Prepend a changelog entry to CHANGELOG.md."""
        changelog_path = self.repo_path / "CHANGELOG.md"
        if changelog_path.exists():
            existing = changelog_path.read_text(errors="replace")
            changelog_path.write_text(entry + existing)
        else:
            header = "# Changelog\n\nAll notable changes to this project.\n\n"
            changelog_path.write_text(header + entry)
        return True

    # ── Git Tagging ──────────────────────────────────────────────────

    async def tag_version(self, version: Version, message: str = "") -> bool:
        """Create a git tag for the new version."""
        tag = f"v{version}"
        msg = message or f"Release {tag}"
        proc = await asyncio.create_subprocess_exec(
            "git", "tag", "-a", tag, "-m", msg,
            cwd=str(self.repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(f"[version-manager] git tag failed: {stderr.decode()[:200]}")
            return False
        logger.info(f"[version-manager] Tagged: {tag}")
        return True

    async def push_tag(self, version: Version) -> bool:
        """Push version tag to remote."""
        tag = f"v{version}"
        proc = await asyncio.create_subprocess_exec(
            "git", "push", "origin", tag,
            cwd=str(self.repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await proc.communicate()
        return proc.returncode == 0
