"""
AI Factory Pipeline v5.6 — Revenue Tracker

Tracks invoices, clients, and revenue for the operator business.
Persisted to Supabase (revenue_invoices + revenue_clients tables).
Falls back to local JSON file if Supabase is unavailable.

Commands: /invoice, /revenue, /clients

Spec Authority: v5.6 §5.x (NB4 Part 25)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("factory.revenue.revenue_tracker")

_LOCAL_FILE = Path(os.getenv("REVENUE_DATA_PATH", "/tmp/ai-factory-revenue.json"))


@dataclass
class Invoice:
    id: str
    client_name: str
    amount: float
    currency: str
    description: str
    project_id: Optional[str]
    operator_id: str
    created_at: str
    notes: str = ""

    @classmethod
    def create(
        cls,
        client_name: str,
        amount: float,
        description: str,
        operator_id: str,
        project_id: Optional[str] = None,
        currency: str = "USD",
        notes: str = "",
    ) -> "Invoice":
        return cls(
            id=str(uuid4())[:8],
            client_name=client_name,
            amount=amount,
            currency=currency,
            description=description,
            project_id=project_id,
            operator_id=operator_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )


@dataclass
class RevenueSummary:
    total_revenue: float
    invoice_count: int
    period: str
    avg_invoice: float
    by_client: dict[str, float] = field(default_factory=dict)
    currency: str = "USD"

    def to_telegram_message(self) -> str:
        lines = [
            f"💰 REVENUE SUMMARY ({self.period})",
            f"",
            f"Total:    ${self.total_revenue:,.2f} {self.currency}",
            f"Invoices: {self.invoice_count}",
            f"Average:  ${self.avg_invoice:,.2f}",
            f"",
        ]
        if self.by_client:
            lines.append("BY CLIENT:")
            for client, total in sorted(
                self.by_client.items(), key=lambda x: -x[1]
            )[:8]:
                lines.append(f"  {client}: ${total:,.2f}")

        return "\n".join(lines)


class RevenueTracker:
    """Track invoices and revenue, persisted to Supabase + local fallback."""

    def __init__(self, operator_id: str) -> None:
        self.operator_id = operator_id

    # ── Storage ───────────────────────────────────────────────────────

    def _load_local(self) -> list[dict]:
        if _LOCAL_FILE.exists():
            try:
                return json.loads(_LOCAL_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_local(self, invoices: list[dict]) -> None:
        _LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_FILE.write_text(json.dumps(invoices, indent=2))

    async def _load_invoices(self) -> list[Invoice]:
        """Load all invoices for this operator (Supabase → local fallback)."""
        try:
            from factory.integrations.supabase import get_supabase_client
            client = get_supabase_client()
            if client:
                result = (
                    client.table("revenue_invoices")
                    .select("*")
                    .eq("operator_id", self.operator_id)
                    .order("created_at", desc=True)
                    .execute()
                )
                if result.data:
                    return [Invoice(**r) for r in result.data]
        except Exception as e:
            logger.debug(f"[revenue] Supabase load failed: {e}")

        raw = [r for r in self._load_local() if r.get("operator_id") == self.operator_id]
        return [Invoice(**r) for r in raw]

    async def _persist_invoice(self, invoice: Invoice) -> bool:
        """Persist invoice to Supabase + local file."""
        saved_supabase = False
        try:
            from factory.integrations.supabase import get_supabase_client
            client = get_supabase_client()
            if client:
                client.table("revenue_invoices").upsert(asdict(invoice)).execute()
                saved_supabase = True
        except Exception as e:
            logger.debug(f"[revenue] Supabase save failed: {e}")

        # Always save locally as backup
        all_invoices = self._load_local()
        all_invoices = [r for r in all_invoices if r.get("id") != invoice.id]
        all_invoices.append(asdict(invoice))
        self._save_local(all_invoices)
        return saved_supabase or True

    # ── Public API ────────────────────────────────────────────────────

    async def log_invoice(
        self,
        client_name: str,
        amount: float,
        description: str,
        project_id: Optional[str] = None,
        currency: str = "USD",
        notes: str = "",
    ) -> Invoice:
        """Create and persist a new invoice."""
        invoice = Invoice.create(
            client_name=client_name,
            amount=amount,
            description=description,
            operator_id=self.operator_id,
            project_id=project_id,
            currency=currency,
            notes=notes,
        )
        await self._persist_invoice(invoice)
        logger.info(f"[revenue] Invoice {invoice.id}: ${amount:.2f} from {client_name}")
        return invoice

    async def get_summary(self, period: str = "all_time") -> RevenueSummary:
        """Return revenue summary for a period (today/this_month/all_time)."""
        invoices = await self._load_invoices()

        if period == "today":
            today = datetime.now(timezone.utc).date().isoformat()
            invoices = [i for i in invoices if i.created_at[:10] == today]
        elif period == "this_month":
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            invoices = [i for i in invoices if i.created_at[:7] == month]

        total  = sum(i.amount for i in invoices)
        count  = len(invoices)
        avg    = total / count if count else 0.0

        by_client: dict[str, float] = {}
        for inv in invoices:
            by_client[inv.client_name] = by_client.get(inv.client_name, 0.0) + inv.amount

        return RevenueSummary(
            total_revenue=total,
            invoice_count=count,
            period=period.replace("_", " ").title(),
            avg_invoice=avg,
            by_client=by_client,
        )

    async def get_recent_invoices(self, limit: int = 10) -> list[Invoice]:
        """Return most recent invoices."""
        invoices = await self._load_invoices()
        return sorted(invoices, key=lambda i: i.created_at, reverse=True)[:limit]

    async def format_invoice_confirmation(self, invoice: Invoice) -> str:
        """Format a Telegram confirmation message for a logged invoice."""
        return (
            f"✅ Invoice logged\n\n"
            f"ID:          #{invoice.id}\n"
            f"Client:      {invoice.client_name}\n"
            f"Amount:      ${invoice.amount:,.2f} {invoice.currency}\n"
            f"Description: {invoice.description}\n"
            f"Date:        {invoice.created_at[:10]}\n"
            + (f"Project:     {invoice.project_id}\n" if invoice.project_id else "")
        )
