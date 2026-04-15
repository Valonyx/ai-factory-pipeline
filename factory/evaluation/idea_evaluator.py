"""
AI Factory Pipeline v5.8 — Idea Evaluator (/evaluate command)

Pre-run feasibility assessment before starting a full pipeline run.
Scores ideas 0–100 across multiple dimensions and recommends whether
to proceed, adjust, or abandon.

Triggered by: /evaluate [idea description] Telegram command

Spec Authority: v5.8 §5.x (NB4 Part 24)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.evaluation.idea_evaluator")

# Score thresholds
_GRADE_THRESHOLDS = {
    "A": 85, "B": 70, "C": 55, "D": 40,
}


@dataclass
class EvaluationScore:
    feasibility:    int   # 0–100: can we build this?
    pipeline_fit:   int   # 0–100: does it fit our 6-stack, 8-stage process?
    complexity:     int   # 0–100: lower = simpler (better for pipeline)
    market_clarity: int   # 0–100: is the use case clear?
    legal_risk:     int   # 0–100: lower = higher risk

    @property
    def overall(self) -> int:
        weights = {
            "feasibility":    0.30,
            "pipeline_fit":   0.25,
            "complexity":     0.20,  # inverted: 100 = simplest
            "market_clarity": 0.15,
            "legal_risk":     0.10,  # inverted: 100 = no risk
        }
        return int(
            self.feasibility    * weights["feasibility"]
            + self.pipeline_fit   * weights["pipeline_fit"]
            + self.complexity     * weights["complexity"]
            + self.market_clarity * weights["market_clarity"]
            + self.legal_risk     * weights["legal_risk"]
        )

    @property
    def grade(self) -> str:
        score = self.overall
        for grade, threshold in _GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"

    @property
    def recommendation(self) -> str:
        g = self.grade
        if g == "A":
            return "✅ Strong match — proceed with /new"
        if g == "B":
            return "✅ Good fit — consider minor adjustments before /new"
        if g == "C":
            return "⚠️ Moderate fit — review challenges before proceeding"
        if g == "D":
            return "⚠️ Poor fit — significant rework needed"
        return "❌ Not recommended — major obstacles identified"


@dataclass
class EvaluationResult:
    idea: str
    score: EvaluationScore
    recommended_stack: str
    time_estimate_minutes: int
    cost_estimate_usd: float
    strengths: list[str] = field(default_factory=list)
    challenges: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    legal_flags: list[str] = field(default_factory=list)
    detailed_analysis: str = ""

    def to_telegram_message(self) -> str:
        s = self.score
        lines = [
            f"📊 IDEA EVALUATION",
            f"",
            f"Idea: {self.idea[:100]}",
            f"",
            f"SCORE: {s.overall}/100  Grade: {s.grade}",
            f"{s.recommendation}",
            f"",
            f"BREAKDOWN:",
            f"  Feasibility:    {s.feasibility}/100",
            f"  Pipeline Fit:   {s.pipeline_fit}/100",
            f"  Simplicity:     {s.complexity}/100",
            f"  Market Clarity: {s.market_clarity}/100",
            f"  Legal Safety:   {s.legal_risk}/100",
            f"",
            f"STACK: {self.recommended_stack}",
            f"EST. TIME: {self.time_estimate_minutes} min pipeline run",
            f"EST. COST: ~${self.cost_estimate_usd:.2f}",
            f"",
        ]
        if self.strengths:
            lines.append("STRENGTHS:")
            for s_item in self.strengths[:3]:
                lines.append(f"  ✓ {s_item}")
            lines.append("")

        if self.challenges:
            lines.append("CHALLENGES:")
            for c in self.challenges[:3]:
                lines.append(f"  ⚠ {c}")
            lines.append("")

        if self.legal_flags:
            lines.append("LEGAL FLAGS:")
            for flag in self.legal_flags[:3]:
                lines.append(f"  🔴 {flag}")
            lines.append("")

        if self.recommendations:
            lines.append("RECOMMENDATIONS:")
            for r in self.recommendations[:3]:
                lines.append(f"  → {r}")
            lines.append("")

        if s.overall >= 70:
            lines.append("→ Ready to build: use /new to start")
        else:
            lines.append("→ Refine your idea before using /new")

        return "\n".join(lines)


class IdeaEvaluator:
    """Evaluate an app idea using Claude before committing to a full pipeline run."""

    async def evaluate(
        self,
        idea: str,
        state: "PipelineState",
    ) -> EvaluationResult:
        """Run AI-powered idea evaluation.

        Uses Claude Strategist to score the idea across 5 dimensions.
        Falls back to rule-based scoring if AI is unavailable.
        """
        try:
            return await self._ai_evaluate(idea, state)
        except Exception as e:
            logger.warning(f"[evaluator] AI eval failed: {e} — using heuristic")
            return self._heuristic_evaluate(idea)

    async def _ai_evaluate(self, idea: str, state: "PipelineState") -> EvaluationResult:
        """Use Claude Strategist to evaluate the idea."""
        from factory.core.roles import call_ai
        from factory.core.state import AIRole

        prompt = f"""You are evaluating an app idea for the AI Factory Pipeline.

APP IDEA: {idea}

The pipeline builds apps using these stacks: FlutterFlow, React Native, Swift, Kotlin, Python Backend, Unity.
It follows stages: Intake → Legal → Blueprint → CodeGen → Build → Test → Deploy → Handoff.
Target market: Saudi Arabia (KSA) and MENA region.

Score the idea 0-100 on each dimension and provide concise analysis.

Respond ONLY as valid JSON:
{{
  "feasibility": <0-100>,
  "pipeline_fit": <0-100>,
  "complexity": <0-100>,
  "market_clarity": <0-100>,
  "legal_risk": <0-100>,
  "recommended_stack": "<flutterflow|react_native|swift|kotlin|python_backend|unity>",
  "time_estimate_minutes": <10-120>,
  "cost_estimate_usd": <0.5-5.0>,
  "strengths": ["<strength1>", "<strength2>", "<strength3>"],
  "challenges": ["<challenge1>", "<challenge2>"],
  "recommendations": ["<rec1>", "<rec2>"],
  "legal_flags": ["<flag1>"] or [],
  "detailed_analysis": "<2-3 sentence summary>"
}}"""

        import json
        response = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=prompt,
            state=state,
            action="general",
        )

        # Extract JSON from response
        json_match = re.search(r"\{[\s\S]+\}", response)
        if not json_match:
            raise ValueError("No JSON in AI response")

        data = json.loads(json_match.group(0))

        score = EvaluationScore(
            feasibility=    int(data.get("feasibility", 70)),
            pipeline_fit=   int(data.get("pipeline_fit", 70)),
            complexity=     int(data.get("complexity", 70)),
            market_clarity= int(data.get("market_clarity", 70)),
            legal_risk=     int(data.get("legal_risk", 70)),
        )

        return EvaluationResult(
            idea=idea,
            score=score,
            recommended_stack=data.get("recommended_stack", "react_native"),
            time_estimate_minutes=int(data.get("time_estimate_minutes", 45)),
            cost_estimate_usd=float(data.get("cost_estimate_usd", 2.0)),
            strengths=data.get("strengths", []),
            challenges=data.get("challenges", []),
            recommendations=data.get("recommendations", []),
            legal_flags=data.get("legal_flags", []),
            detailed_analysis=data.get("detailed_analysis", ""),
        )

    def _heuristic_evaluate(self, idea: str) -> EvaluationResult:
        """Simple rule-based fallback if AI is unavailable."""
        idea_lower = idea.lower()
        words = idea.split()

        # Quick heuristics
        has_ksa   = any(kw in idea_lower for kw in ["saudi", "ksa", "arabic", "riyadh"])
        is_mobile = any(kw in idea_lower for kw in ["app", "mobile", "ios", "android"])
        is_web    = any(kw in idea_lower for kw in ["website", "web", "dashboard", "portal"])
        has_legal = any(kw in idea_lower for kw in ["payment", "finance", "medical", "health"])
        is_complex = len(words) > 50 or any(kw in idea_lower for kw in ["ai", "blockchain", "ml", "realtime"])

        complexity = 40 if is_complex else 75
        legal_risk = 50 if has_legal else 85
        stack = "react_native" if is_mobile else ("python_backend" if is_web else "flutterflow")
        time_est = 90 if is_complex else 45

        score = EvaluationScore(
            feasibility=75,
            pipeline_fit=70 if is_mobile or is_web else 55,
            complexity=complexity,
            market_clarity=80 if has_ksa else 65,
            legal_risk=legal_risk,
        )
        return EvaluationResult(
            idea=idea,
            score=score,
            recommended_stack=stack,
            time_estimate_minutes=time_est,
            cost_estimate_usd=1.5,
            strengths=["Idea is clear enough to proceed", "Fits pipeline capabilities"],
            challenges=["AI analysis unavailable — manual review recommended"],
            recommendations=["Review the idea in detail before starting", "Consider legal requirements for KSA"],
        )
