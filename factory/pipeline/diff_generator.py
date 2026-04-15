"""
AI Factory Pipeline v5.8 — Diff Generator (MODIFY Mode)

Generates unified diffs between original and AI-modified files.
Used in MODIFY mode (S3 CodeGen) to produce reviewable change sets
instead of full file rewrites.

Spec Authority: v5.6 §4.0 (NB4 Part 21-22)
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("factory.pipeline.diff_generator")


@dataclass
class FileDiff:
    path: str
    original: str        # Original file content (empty string for new files)
    modified: str        # New file content (empty string for deleted files)
    is_new: bool = False
    is_deleted: bool = False
    unified_diff: str = ""
    lines_added: int = 0
    lines_removed: int = 0

    def __post_init__(self):
        if not self.unified_diff and not self.is_new and not self.is_deleted:
            self.unified_diff = generate_unified_diff(
                self.original, self.modified, self.path,
            )
            self.lines_added, self.lines_removed = _count_diff_lines(self.unified_diff)


@dataclass
class ChangeSet:
    """Complete set of changes for a MODIFY operation."""
    modified_files: list[FileDiff] = field(default_factory=list)
    new_files: list[FileDiff] = field(default_factory=list)
    deleted_files: list[FileDiff] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.modified_files) + len(self.new_files) + len(self.deleted_files)

    @property
    def lines_added(self) -> int:
        return sum(f.lines_added for f in self.modified_files + self.new_files)

    @property
    def lines_removed(self) -> int:
        return sum(f.lines_removed for f in self.modified_files + self.deleted_files)

    def to_review_text(self) -> str:
        """Format the changeset for operator review via Telegram."""
        lines = [
            f"📋 CHANGE SET SUMMARY",
            f"Modified: {len(self.modified_files)} files",
            f"New:      {len(self.new_files)} files",
            f"Deleted:  {len(self.deleted_files)} files",
            f"Lines:    +{self.lines_added} / -{self.lines_removed}",
            "",
        ]

        for f in self.new_files[:5]:
            lines.append(f"✅ NEW: {f.path}")

        for f in self.deleted_files[:5]:
            lines.append(f"🗑 DEL: {f.path}")

        for f in self.modified_files[:10]:
            lines.append(f"✏️ MOD: {f.path} (+{f.lines_added}/-{f.lines_removed})")

        if len(self.modified_files) > 10:
            lines.append(f"... and {len(self.modified_files) - 10} more modified files")

        return "\n".join(lines)

    def to_full_diff_text(self, max_chars: int = 30_000) -> str:
        """Full unified diff text for all changes."""
        parts: list[str] = []
        budget = max_chars

        for f in self.new_files:
            block = f"=== NEW FILE: {f.path} ===\n{f.modified[:3000]}\n"
            if len(block) < budget:
                parts.append(block)
                budget -= len(block)

        for f in self.deleted_files:
            block = f"=== DELETED: {f.path} ===\n"
            parts.append(block)

        for f in self.modified_files:
            block = f"=== {f.path} ===\n{f.unified_diff[:3000]}\n"
            if len(block) < budget:
                parts.append(block)
                budget -= len(block)

        return "\n".join(parts)


def generate_unified_diff(
    original: str,
    modified: str,
    file_path: str,
    context_lines: int = 3,
) -> str:
    """Generate a unified diff string (git-style)."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines  = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )
    return "".join(diff)


def build_changeset(
    original_files: dict[str, str],
    generated_files: dict[str, str],
) -> ChangeSet:
    """Build a ChangeSet from original and generated file dicts.

    Args:
        original_files: {path: content} of existing codebase files
        generated_files: {path: content} of AI-generated changes

    Returns:
        ChangeSet with modified, new, and deleted files.
    """
    cs = ChangeSet()

    orig_keys = set(original_files)
    gen_keys  = set(generated_files)

    # New files
    for path in gen_keys - orig_keys:
        cs.new_files.append(FileDiff(
            path=path,
            original="",
            modified=generated_files[path],
            is_new=True,
            lines_added=generated_files[path].count("\n"),
        ))

    # Deleted files
    for path in orig_keys - gen_keys:
        cs.deleted_files.append(FileDiff(
            path=path,
            original=original_files[path],
            modified="",
            is_deleted=True,
            lines_removed=original_files[path].count("\n"),
        ))

    # Modified files
    for path in orig_keys & gen_keys:
        orig = original_files[path]
        mod  = generated_files[path]
        if orig != mod:
            cs.modified_files.append(FileDiff(
                path=path,
                original=orig,
                modified=mod,
            ))

    return cs


def _count_diff_lines(diff_text: str) -> tuple[int, int]:
    """Count added and removed lines from a unified diff."""
    added   = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))
    return added, removed


def apply_changeset(
    changeset: ChangeSet,
    base_files: dict[str, str],
) -> dict[str, str]:
    """Apply a changeset to a base file dict, producing merged result.

    Returns updated {path: content} dict.
    """
    result = dict(base_files)

    for f in changeset.new_files:
        result[f.path] = f.modified

    for f in changeset.deleted_files:
        result.pop(f.path, None)

    for f in changeset.modified_files:
        result[f.path] = f.modified

    return result
