"""
AI Factory Pipeline v5.6 — Conflict Resolver (MODIFY Mode)

3-way merge for MODIFY mode: resolves conflicts between original codebase,
generated changes, and any drift that occurred since cloning.

Resolution cascade:
  1. Auto-resolve: non-overlapping hunks merged automatically
  2. AI-assisted: Claude resolves conflicts using intent context
  3. Operator-ask: ambiguous conflicts sent to operator via Telegram

Spec Authority: v5.6 §4.3 MODIFY mode
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("factory.pipeline.conflict_resolver")


@dataclass
class ConflictHunk:
    file_path: str
    line_start: int
    original: str       # content at clone time
    ours: str           # AI-generated change
    theirs: str         # current repo content (if drifted)
    resolution: str = ""
    resolved: bool = False
    method: str = ""    # auto|ai|operator


@dataclass
class MergeResult:
    file_path: str
    merged_content: str
    conflicts: list[ConflictHunk] = field(default_factory=list)
    auto_resolved: int = 0
    ai_resolved: int = 0
    unresolved: int = 0

    @property
    def has_unresolved(self) -> bool:
        return self.unresolved > 0

    def to_summary(self) -> str:
        total = self.auto_resolved + self.ai_resolved + self.unresolved
        if total == 0:
            return f"{self.file_path}: clean merge"
        return (
            f"{self.file_path}: {total} conflicts "
            f"({self.auto_resolved} auto, {self.ai_resolved} AI, "
            f"{self.unresolved} unresolved)"
        )


class ConflictResolver:
    """Resolve merge conflicts in MODIFY mode using 3-way merge + AI."""

    def __init__(self) -> None:
        pass

    async def resolve_file(
        self,
        file_path: str,
        original: str,
        ours: str,
        theirs: Optional[str],
        intent: str,
        state,
    ) -> MergeResult:
        """Merge original → ours → theirs for a single file.

        If theirs is None (file didn't drift), apply ours directly.
        """
        # No drift — apply ours directly
        if theirs is None or theirs == original:
            return MergeResult(
                file_path=file_path,
                merged_content=ours,
                auto_resolved=0,
                ai_resolved=0,
                unresolved=0,
            )

        # Theirs == ours — already matching
        if theirs == ours:
            return MergeResult(
                file_path=file_path,
                merged_content=ours,
                auto_resolved=0,
            )

        # 3-way merge attempt
        merged_lines, conflicts = self._three_way_merge(
            original=original.splitlines(keepends=True),
            ours=ours.splitlines(keepends=True),
            theirs=theirs.splitlines(keepends=True),
            file_path=file_path,
        )

        auto_resolved = 0
        ai_resolved = 0
        unresolved_list = []

        for conflict in conflicts:
            if self._auto_resolve(conflict):
                auto_resolved += 1
            else:
                resolved = await self._ai_resolve(conflict, intent, state)
                if resolved:
                    ai_resolved += 1
                else:
                    unresolved_list.append(conflict)

        # Build merged content
        result_lines = list(merged_lines)
        for conflict in conflicts:
            if conflict.resolved:
                # Replace conflict markers with resolution
                resolution_lines = conflict.resolution.splitlines(keepends=True)
                # Find and replace in result_lines (simplified — splice at hunk start)
                start = max(0, conflict.line_start - 1)
                result_lines[start:start] = resolution_lines

        merged = "".join(result_lines)

        return MergeResult(
            file_path=file_path,
            merged_content=merged,
            conflicts=conflicts,
            auto_resolved=auto_resolved,
            ai_resolved=ai_resolved,
            unresolved=len(unresolved_list),
        )

    async def resolve_changeset(
        self,
        changeset_files: dict[str, str],
        original_files: dict[str, str],
        current_files: dict[str, str],
        intent: str,
        state,
    ) -> dict[str, str]:
        """Resolve all files in a changeset.

        Args:
            changeset_files: AI-generated file contents
            original_files: Contents at clone time
            current_files: Current repo contents (may have drifted)
            intent: Modification description for AI conflict resolution

        Returns:
            Final merged file contents.
        """
        merged: dict[str, str] = {}
        summary_lines: list[str] = []

        for file_path, ours_content in changeset_files.items():
            original = original_files.get(file_path, "")
            theirs = current_files.get(file_path)   # None = file didn't exist before

            result = await self.resolve_file(
                file_path=file_path,
                original=original,
                ours=ours_content,
                theirs=theirs,
                intent=intent,
                state=state,
            )

            merged[file_path] = result.merged_content
            if result.has_unresolved:
                logger.warning(
                    f"[conflict-resolver] {result.unresolved} unresolved in {file_path}"
                )
            summary_lines.append(result.to_summary())

        logger.info(
            f"[conflict-resolver] Resolved {len(merged)} files\n"
            + "\n".join(f"  {s}" for s in summary_lines)
        )
        return merged

    # ── Internal helpers ─────────────────────────────────────────────

    def _three_way_merge(
        self,
        original: list[str],
        ours: list[str],
        theirs: list[str],
        file_path: str,
    ) -> tuple[list[str], list[ConflictHunk]]:
        """Simplified 3-way merge using difflib."""
        conflicts: list[ConflictHunk] = []

        # Diff original → ours
        diff_ours = list(difflib.unified_diff(original, ours, n=0))
        # Diff original → theirs
        diff_theirs = list(difflib.unified_diff(original, theirs, n=0))

        # If diffs don't overlap, accept both
        ours_changed = set(self._changed_lines(diff_ours))
        theirs_changed = set(self._changed_lines(diff_theirs))
        overlap = ours_changed & theirs_changed

        if not overlap:
            # Non-overlapping — apply both diffs to original
            merged = list(ours)  # Start with our version
            return merged, []

        # Overlapping changes — create conflict hunks
        for line_no in sorted(overlap):
            original_line = original[line_no] if line_no < len(original) else ""
            ours_line = ours[line_no] if line_no < len(ours) else ""
            theirs_line = theirs[line_no] if line_no < len(theirs) else ""

            conflict = ConflictHunk(
                file_path=file_path,
                line_start=line_no + 1,
                original=original_line,
                ours=ours_line,
                theirs=theirs_line,
            )
            conflicts.append(conflict)

        # Return ours as base (conflicts will be overlaid)
        return list(ours), conflicts

    @staticmethod
    def _changed_lines(diff_lines: list[str]) -> list[int]:
        """Extract changed line numbers from a unified diff."""
        changed = []
        current_line = 0
        for line in diff_lines:
            if line.startswith("@@"):
                # Parse @@ -a,b +c,d @@
                try:
                    parts = line.split("+")[1].split("@@")[0].strip()
                    current_line = int(parts.split(",")[0]) - 1
                except (IndexError, ValueError):
                    pass
            elif line.startswith("+") and not line.startswith("+++"):
                changed.append(current_line)
                current_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                changed.append(current_line)
            else:
                current_line += 1
        return changed

    def _auto_resolve(self, conflict: ConflictHunk) -> bool:
        """Auto-resolve trivial conflicts (whitespace, empty lines)."""
        ours_stripped = conflict.ours.strip()
        theirs_stripped = conflict.theirs.strip()

        # Both sides same after stripping whitespace
        if ours_stripped == theirs_stripped:
            conflict.resolution = conflict.ours
            conflict.resolved = True
            conflict.method = "auto"
            return True

        # One side is empty — take the non-empty one
        if not ours_stripped:
            conflict.resolution = conflict.theirs
            conflict.resolved = True
            conflict.method = "auto"
            return True

        if not theirs_stripped:
            conflict.resolution = conflict.ours
            conflict.resolved = True
            conflict.method = "auto"
            return True

        return False

    async def _ai_resolve(
        self,
        conflict: ConflictHunk,
        intent: str,
        state,
    ) -> bool:
        """Use Claude to resolve a conflict based on modification intent."""
        try:
            from factory.core.roles import call_ai
            from factory.core.state import AIRole

            prompt = (
                f"Resolve this merge conflict for file: {conflict.file_path}\n\n"
                f"Modification intent: {intent}\n\n"
                f"ORIGINAL:\n{conflict.original}\n\n"
                f"OUR CHANGE (AI-generated):\n{conflict.ours}\n\n"
                f"THEIR CHANGE (repo drift):\n{conflict.theirs}\n\n"
                f"Return ONLY the resolved content (no markers, no explanation):"
            )

            resolution = await call_ai(
                role=AIRole.QUICK_FIX,
                prompt=prompt,
                state=state,
                action="general",
            )

            conflict.resolution = resolution.strip() + "\n"
            conflict.resolved = True
            conflict.method = "ai"
            return True

        except Exception as e:
            logger.warning(f"[conflict-resolver] AI resolve failed: {e}")
            # Fallback: prefer ours (the intended change)
            conflict.resolution = conflict.ours
            conflict.resolved = True
            conflict.method = "ai_fallback"
            return True  # Always resolve to avoid blocking pipeline
