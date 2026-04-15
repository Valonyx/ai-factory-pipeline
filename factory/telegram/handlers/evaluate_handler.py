"""
AI Factory Pipeline v5.8 — /evaluate Command Handler

Scores an app idea on 5 dimensions using Claude Strategist.
Usage: /evaluate <app idea description>

Spec Authority: v5.6 §5.2 (/evaluate)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("factory.telegram.handlers.evaluate")


async def cmd_evaluate(update: Any, context: Any) -> None:
    """/evaluate <idea> — Score an app idea (0-100) on 5 dimensions."""
    user_id = str(update.effective_user.id)

    idea = " ".join(context.args) if context.args else ""
    if not idea:
        await update.message.reply_text(
            "Usage: /evaluate <your app idea>\n\n"
            "Example: /evaluate A food delivery app for gym-goers with macro tracking"
        )
        return

    await update.message.reply_text(
        f"Evaluating: \"{idea[:100]}...\"\n\nAnalyzing..."
        if len(idea) > 100
        else f"Evaluating: \"{idea}\"\n\nAnalyzing..."
    )

    try:
        from factory.evaluation.idea_evaluator import IdeaEvaluator
        from factory.core.state import PipelineState

        # Minimal state for AI calls
        state = PipelineState(
            project_id=f"eval_{user_id[:6]}",
            operator_id=user_id,
        )

        evaluator = IdeaEvaluator()
        result = await evaluator.evaluate(idea=idea, state=state)

        await update.message.reply_text(result.to_telegram_message())

    except Exception as e:
        logger.error(f"[evaluate] Error for {user_id}: {e}")
        await update.message.reply_text(
            "Evaluation failed. Please try again.\n"
            f"Error: {str(e)[:100]}"
        )
