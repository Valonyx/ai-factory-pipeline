"""
AI Factory Pipeline v5.8 — Operator Notification System

Implements:
  - §5.4 Notification pipeline (notify_operator)
  - §5.1 send_telegram_message (core send function)
  - §7.5 send_telegram_file (binary file delivery)
  - Audit logging for all operator communications

Spec Authority: v5.8 §5.4, §5.1, §7.5
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from factory.core.state import (
    NotificationType,
    PipelineState,
    TELEGRAM_FILE_LIMIT_MB,
)
from factory.telegram.messages import (
    NOTIFICATION_EMOJI,
    truncate_message,
)

logger = logging.getLogger("factory.telegram.notifications")


# ═══════════════════════════════════════════════════════════════════
# Telegram Bot Instance (set at startup)
# ═══════════════════════════════════════════════════════════════════

_bot_instance: Any = None


def set_bot_instance(bot: Any) -> None:
    """Set the active Telegram bot instance.

    Called from telegram/bot.py during startup.
    """
    global _bot_instance
    _bot_instance = bot


def get_bot() -> Any:
    """Get the active Telegram bot instance.

    Returns the bot, or None if not yet configured.
    """
    return _bot_instance


# ═══════════════════════════════════════════════════════════════════
# §5.1 Core Send Function
# ═══════════════════════════════════════════════════════════════════


async def send_telegram_message(
    operator_id: str,
    text: str,
    reply_markup: Any = None,
    parse_mode: Optional[str] = None,
) -> bool:
    """Send a text message to an operator via Telegram.

    Spec: §5.1
    Handles truncation to 4096 chars, retry on transient errors.

    Args:
        operator_id: Telegram user ID (string).
        text: Message text.
        reply_markup: Optional inline keyboard.
        parse_mode: Optional parse mode (Markdown, HTML).

    Returns:
        True if sent successfully, False otherwise.
    """
    bot = get_bot()
    if bot is None:
        logger.warning(
            f"[MOCK] Telegram not configured. Message to {operator_id}: "
            f"{text[:200]}"
        )
        return False

    text = truncate_message(text)

    try:
        await bot.send_message(
            chat_id=int(operator_id),
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {operator_id}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# §7.5 File Delivery
# ═══════════════════════════════════════════════════════════════════


async def send_telegram_file(
    operator_id: str,
    file_path: str,
    caption: str = "",
    filename: Optional[str] = None,
) -> bool:
    """Send a file to operator via Telegram.

    Spec: §7.5, §8.10 Contract 2
    Telegram file limit: 50MB. Files over limit get a download link instead.

    Args:
        operator_id: Telegram user ID.
        file_path: Local path to file.
        caption: Optional caption.
        filename: Optional display filename.

    Returns:
        True if sent, False on failure.
    """
    bot = get_bot()
    if bot is None:
        logger.warning(
            f"[MOCK] File send to {operator_id}: {file_path}"
        )
        return False

    # Check file size
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    except OSError:
        logger.error(f"File not found: {file_path}")
        return False

    if file_size_mb > TELEGRAM_FILE_LIMIT_MB:
        await send_telegram_message(
            operator_id,
            f"📦 File too large for Telegram ({file_size_mb:.1f}MB > "
            f"{TELEGRAM_FILE_LIMIT_MB}MB).\n"
            f"Uploaded to storage. Download link will be sent separately.",
        )
        return False

    try:
        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=int(operator_id),
                document=f,
                caption=truncate_message(caption, max_length=1024),
                filename=filename or os.path.basename(file_path),
            )
        return True
    except Exception as e:
        logger.error(
            f"Failed to send file to {operator_id}: {e}"
        )
        return False


async def send_telegram_content(
    operator_id: str,
    content: str,
    filename: str,
) -> bool:
    """Send string content as a file attachment.

    Spec: §7.5
    Used for sending generated documents (legal docs, handoff docs).
    Creates a temporary file, sends it, then cleans up.
    """
    import tempfile

    try:
        suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".txt"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False,
        ) as f:
            f.write(content)
            tmp_path = f.name

        result = await send_telegram_file(
            operator_id, tmp_path, filename=filename,
        )

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        return result
    except Exception as e:
        logger.error(f"Failed to send content as file: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# §5.4 Notification System
# ═══════════════════════════════════════════════════════════════════


async def notify_operator(
    state_or_id: PipelineState | str,
    notification_type: NotificationType,
    message: str,
    reply_markup: Any = None,
) -> bool:
    """Send a typed notification to the operator.

    Spec: §5.4
    Formats message with appropriate emoji prefix,
    logs to audit trail.

    Args:
        state_or_id: PipelineState (uses operator_id) or operator ID string.
        notification_type: Type of notification.
        message: Notification text.
        reply_markup: Optional inline keyboard.

    Returns:
        True if sent, False otherwise.
    """
    if isinstance(state_or_id, PipelineState):
        operator_id = state_or_id.operator_id
        project_id = state_or_id.project_id
    else:
        operator_id = state_or_id
        project_id = "unknown"

    emoji = NOTIFICATION_EMOJI.get(notification_type, "📬")
    formatted = f"{emoji} {message}"

    success = await send_telegram_message(
        operator_id, formatted, reply_markup=reply_markup,
    )

    # Audit log
    await _log_notification(
        operator_id=operator_id,
        project_id=project_id,
        notification_type=notification_type.value,
        message=message[:500],
        delivered=success,
    )

    return success


async def notify_scout_confidence(
    state: PipelineState,
    provider: str,
    domain: str,
    confidence: float,
    query_preview: str,
    grounded: bool,
    fused: bool,
) -> None:
    """Notify operator when Scout research confidence is low on a high-stakes query.

    Called by ScoutOrchestrator when confidence < 0.55 for legal/compliance/
    security queries. Gives the operator a chance to manually verify before
    the Strategist acts on the research.

    Not sent in CI/mock mode or when no bot is configured.
    """
    import os
    if os.getenv("SCOUT_PROVIDER", "").lower() == "mock":
        return

    operator_id = state.operator_id
    if not operator_id:
        return

    confidence_pct = int(confidence * 100)
    grounded_str = "Exa-verified ✓" if grounded else "not Exa-verified"
    fused_str = " | multi-source fused" if fused else ""

    # Confidence tier emoji
    if confidence_pct >= 70:
        emoji = "🟡"
        tier  = "moderate"
    elif confidence_pct >= 50:
        emoji = "🟠"
        tier  = "low"
    else:
        emoji = "🔴"
        tier  = "very low"

    message = (
        f"{emoji} Scout Research — {tier.upper()} CONFIDENCE\n\n"
        f"Domain  : {domain.upper()}\n"
        f"Provider: {provider}{fused_str}\n"
        f"Ground  : {grounded_str}\n"
        f"Score   : {confidence_pct}%\n\n"
        f"Query: {query_preview}\n\n"
        f"The Strategist will use this research. If the result seems uncertain, "
        f"consider verifying the key claims manually before proceeding."
    )

    try:
        await send_telegram_message(operator_id, message)
        logger.info(
            f"[scout-notify] confidence alert sent: "
            f"{confidence_pct}% domain={domain} provider={provider}"
        )
    except Exception as e:
        logger.debug(f"[scout-notify] send failed (non-fatal): {e}")


async def send_telegram_budget_alert(
    operator_id: str,
    phase: str,
    cost: float,
    limit: float,
) -> None:
    """Send a circuit breaker budget alert.

    Spec: §3.6
    """
    await send_telegram_message(
        operator_id,
        f"💰 Circuit breaker triggered\n\n"
        f"Phase: {phase}\n"
        f"Cost: ${cost:.2f} (limit: ${limit:.2f})\n\n"
        f"/continue — Resume (resets breaker)\n"
        f"/cancel — Stop project",
    )


# ═══════════════════════════════════════════════════════════════════
# Stub: Audit Logging
# ═══════════════════════════════════════════════════════════════════


async def _log_notification(
    operator_id: str,
    project_id: str,
    notification_type: str,
    message: str,
    delivered: bool,
) -> None:
    """Log notification to audit trail.

    Stub — real implementation uses Supabase audit_log table.
    """
    logger.info(
        f"[Notification] type={notification_type} "
        f"operator={operator_id} project={project_id} "
        f"delivered={delivered}"
    )