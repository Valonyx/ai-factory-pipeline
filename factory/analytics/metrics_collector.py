"""
AI Factory Pipeline v5.6 — Metrics Collector (/analytics command)

Tracks and reports pipeline performance metrics:
  • Pipeline runs: success rate, avg duration
  • Costs: per-phase, per-stack, totals
  • Build outcomes by stack
  • Operator productivity

Persisted to Supabase (pipeline_metrics table) + local JSON fallback.

Spec Authority: v5.6 §5.x (NB4 Part 26)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("factory.analytics.metrics_collector")

_LOCAL_FILE = Path(os.getenv("METRICS_DATA_PATH", "/tmp/ai-factory-metrics.json"))


@dataclass
class PipelineRun:
    project_id: str
    operator_id: str
    stack: str
    pipeline_mode: str
    started_at: str
    completed_at: Optional[str]
    success: bool
    total_cost_usd: float
    duration_seconds: float
    stages_completed: int
    error_stage: Optional[str] = None
    deployment_targets: list = field(default_factory=list)


class MetricsCollector:
    """Record and query pipeline metrics."""

    def __init__(self, operator_id: str) -> None:
        self.operator_id = operator_id

    def _load_local(self) -> list[dict]:
        if _LOCAL_FILE.exists():
            try:
                return json.loads(_LOCAL_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_local(self, runs: list[dict]) -> None:
        _LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_FILE.write_text(json.dumps(runs, indent=2))

    async def record_run(self, run: PipelineRun) -> None:
        """Persist a completed pipeline run."""
        try:
            from factory.integrations.supabase import get_supabase_client
            client = get_supabase_client()
            if client:
                client.table("pipeline_metrics").upsert(asdict(run)).execute()
        except Exception:
            pass
        all_runs = self._load_local()
        all_runs = [r for r in all_runs if r.get("project_id") != run.project_id]
        all_runs.append(asdict(run))
        self._save_local(all_runs)

    async def _load_runs(self, days: int = 30) -> list[PipelineRun]:
        """Load runs for this operator within the last N days."""
        try:
            from factory.integrations.supabase import get_supabase_client
            client = get_supabase_client()
            if client:
                from datetime import timedelta
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                result = (
                    client.table("pipeline_metrics")
                    .select("*")
                    .eq("operator_id", self.operator_id)
                    .gte("started_at", cutoff)
                    .execute()
                )
                if result.data:
                    return [PipelineRun(**r) for r in result.data]
        except Exception:
            pass

        all_runs = [
            r for r in self._load_local()
            if r.get("operator_id") == self.operator_id
        ]
        return [PipelineRun(**r) for r in all_runs]

    async def get_dashboard(self, period: str = "30d") -> str:
        """Generate analytics dashboard for Telegram."""
        days = int(period.replace("d", "")) if "d" in period else 30
        runs = await self._load_runs(days)

        if not runs:
            return (
                f"📈 ANALYTICS ({period})\n\n"
                f"No pipeline runs recorded yet.\n\n"
                f"Start your first project with /new!"
            )

        total     = len(runs)
        succeeded = sum(1 for r in runs if r.success)
        failed    = total - succeeded
        rate      = int(succeeded / total * 100) if total else 0

        total_cost = sum(r.total_cost_usd for r in runs)
        avg_cost   = total_cost / total if total else 0
        avg_dur    = sum(r.duration_seconds for r in runs) / total if total else 0
        avg_dur_m  = int(avg_dur / 60)

        # By stack
        by_stack: dict[str, dict] = {}
        for r in runs:
            if r.stack not in by_stack:
                by_stack[r.stack] = {"total": 0, "success": 0, "cost": 0.0}
            by_stack[r.stack]["total"] += 1
            by_stack[r.stack]["success"] += int(r.success)
            by_stack[r.stack]["cost"] += r.total_cost_usd

        lines = [
            f"📈 ANALYTICS (last {days} days)",
            f"",
            f"PIPELINE RUNS",
            f"  Total:    {total}",
            f"  Success:  {succeeded} ({rate}%)",
            f"  Failed:   {failed}",
            f"  Avg time: {avg_dur_m} min",
            f"",
            f"COSTS",
            f"  Total:    ${total_cost:.2f}",
            f"  Avg/run:  ${avg_cost:.2f}",
            f"",
        ]

        if by_stack:
            lines.append("BY STACK")
            for stack, data in sorted(by_stack.items(), key=lambda x: -x[1]["total"]):
                sr = int(data["success"] / data["total"] * 100)
                lines.append(
                    f"  {stack}: {data['total']} runs, {sr}% success, ${data['cost']:.2f}"
                )
            lines.append("")

        # Modify mode stats
        modify_runs = [r for r in runs if r.pipeline_mode == "modify"]
        if modify_runs:
            lines.append(f"MODIFY MODE: {len(modify_runs)} runs")

        return "\n".join(lines)

    async def record_from_state(self, state) -> None:
        """Convenience method: record a run from a completed PipelineState."""
        from factory.core.state import Stage
        now = datetime.now(timezone.utc).isoformat()

        stages_map = {
            Stage.S0_INTAKE: 0, Stage.S1_LEGAL: 1, Stage.S2_BLUEPRINT: 2,
            Stage.S4_CODEGEN: 3, Stage.S5_BUILD: 4, Stage.S6_TEST: 5,
            Stage.S7_DEPLOY: 6, Stage.S8_VERIFY: 7, Stage.S9_HANDOFF: 8,
            Stage.COMPLETED: 9,
        }
        stages_done = stages_map.get(state.current_stage, 0)
        success = state.current_stage == Stage.COMPLETED

        run = PipelineRun(
            project_id=state.project_id,
            operator_id=state.operator_id,
            stack=state.selected_stack.value if state.selected_stack else "unknown",
            pipeline_mode=state.pipeline_mode.value if hasattr(state, "pipeline_mode") else "create",
            started_at=now,
            completed_at=now,
            success=success,
            total_cost_usd=state.total_cost_usd,
            duration_seconds=0.0,
            stages_completed=stages_done,
            error_stage=None if success else state.current_stage.value,
            deployment_targets=(state.s7_output or {}).get("deployments", {}).keys(),
        )
        await self.record_run(run)
