"""
AI Factory Pipeline v5.6 — Revenue Command Handlers

/invoice <client> <amount> <description> — Log an invoice
/revenue [today|this_month|all_time]     — Show revenue summary
/clients                                  — List all clients

Spec Authority: v5.6 §5.2 (/invoice, /revenue, /clients), NB4 Part 25
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("factory.telegram.handlers.revenue")


async def cmd_invoice(update: Any, context: Any) -> None:
    """/invoice <client> <amount> <description...> — Log an invoice."""
    user_id = str(update.effective_user.id)

    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /invoice <client_name> <amount> <description>\n\n"
            "Example: /invoice \"Acme Corp\" 1500 \"Flutter app development\""
        )
        return

    # Parse: first arg = client, second = amount, rest = description
    client_name = context.args[0].strip('"\'')
    try:
        amount = float(context.args[1].replace(",", "").replace("$", ""))
    except ValueError:
        await update.message.reply_text(
            f"Invalid amount: {context.args[1]}\n"
            "Use a number like 1500 or 1500.00"
        )
        return

    description = " ".join(context.args[2:]).strip('"\'')

    try:
        from factory.revenue.revenue_tracker import RevenueTracker
        from factory.revenue.customer_manager import CustomerManager

        tracker = RevenueTracker(operator_id=user_id)
        customers = CustomerManager(operator_id=user_id)

        # Find active project for linking
        project_id = None
        try:
            from factory.telegram.bot import get_active_project
            active = await get_active_project(user_id)
            if active:
                project_id = active.get("project_id")
        except Exception:
            pass

        # Log invoice
        invoice = await tracker.log_invoice(
            client_name=client_name,
            amount=amount,
            description=description,
            project_id=project_id,
        )

        # Update customer record
        customer = await customers.get_or_create(name=client_name)
        await customers.add_invoice_total(client_name, amount)
        if project_id:
            await customers.link_project(customer.id, project_id)

        confirmation = await tracker.format_invoice_confirmation(invoice)
        await update.message.reply_text(confirmation)

    except Exception as e:
        logger.error(f"[invoice] Error for {user_id}: {e}")
        await update.message.reply_text(f"Failed to log invoice: {str(e)[:100]}")


async def cmd_revenue(update: Any, context: Any) -> None:
    """/revenue [today|this_month|all_time] — Show revenue summary."""
    user_id = str(update.effective_user.id)

    period = "all_time"
    if context.args:
        arg = context.args[0].lower()
        if arg in ("today", "this_month", "all_time"):
            period = arg
        elif arg in ("month", "monthly"):
            period = "this_month"

    try:
        from factory.revenue.revenue_tracker import RevenueTracker

        tracker = RevenueTracker(operator_id=user_id)
        summary = await tracker.get_summary(period=period)
        await update.message.reply_text(summary.to_telegram_message())

    except Exception as e:
        logger.error(f"[revenue] Error for {user_id}: {e}")
        await update.message.reply_text(f"Failed to load revenue: {str(e)[:100]}")


async def cmd_clients(update: Any, context: Any) -> None:
    """/clients — List all clients sorted by total invoiced."""
    user_id = str(update.effective_user.id)

    try:
        from factory.revenue.customer_manager import CustomerManager

        manager = CustomerManager(operator_id=user_id)
        message = await manager.format_clients_list()
        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"[clients] Error for {user_id}: {e}")
        await update.message.reply_text(f"Failed to load clients: {str(e)[:100]}")
