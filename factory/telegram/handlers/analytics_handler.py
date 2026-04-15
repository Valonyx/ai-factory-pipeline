"""
AI Factory Pipeline v5.8 — /analytics Command Handler

/analytics [7d|30d|90d] — Pipeline performance dashboard

Spec Authority: v5.6 §5.2 (/analytics), NB4 Part 26
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("factory.telegram.handlers.analytics")


async def cmd_analytics(update: Any, context: Any) -> None:
    """/analytics [7d|30d|90d] — Show pipeline performance dashboard."""
    user_id = str(update.effective_user.id)

    period = "30d"
    if context.args:
        arg = context.args[0].lower().replace("days", "d").replace("day", "d")
        if arg in ("7d", "30d", "90d", "7", "30", "90"):
            period = arg if arg.endswith("d") else f"{arg}d"

    try:
        from factory.analytics.metrics_collector import MetricsCollector

        collector = MetricsCollector(operator_id=user_id)
        dashboard = await collector.get_dashboard(period=period)
        await update.message.reply_text(dashboard)

    except Exception as e:
        logger.error(f"[analytics] Error for {user_id}: {e}")
        await update.message.reply_text(f"Failed to load analytics: {str(e)[:100]}")
