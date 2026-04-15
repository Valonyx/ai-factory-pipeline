"""
AI Factory Pipeline v5.8 — Customer Manager (/clients command)

Manages customer records for the operator business.
Persisted to Supabase (revenue_clients table) + local JSON fallback.

Spec Authority: v5.8 §5.x (NB4 Part 25-26)
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

logger = logging.getLogger("factory.revenue.customer_manager")

_LOCAL_FILE = Path(os.getenv("CUSTOMERS_DATA_PATH", "/tmp/ai-factory-customers.json"))


@dataclass
class Customer:
    id: str
    name: str
    operator_id: str
    email: str = ""
    phone: str = ""
    company: str = ""
    project_ids: list = field(default_factory=list)
    total_invoiced: float = 0.0
    created_at: str = ""
    notes: str = ""

    @classmethod
    def create(
        cls,
        name: str,
        operator_id: str,
        email: str = "",
        phone: str = "",
        company: str = "",
    ) -> "Customer":
        return cls(
            id=str(uuid4())[:8],
            name=name,
            operator_id=operator_id,
            email=email,
            phone=phone,
            company=company,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class CustomerManager:
    """Create and retrieve customer records."""

    def __init__(self, operator_id: str) -> None:
        self.operator_id = operator_id

    def _load_local(self) -> list[dict]:
        if _LOCAL_FILE.exists():
            try:
                return json.loads(_LOCAL_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_local(self, customers: list[dict]) -> None:
        _LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_FILE.write_text(json.dumps(customers, indent=2))

    async def _load_all(self) -> list[Customer]:
        try:
            from factory.integrations.supabase import get_supabase_client
            client = get_supabase_client()
            if client:
                result = (
                    client.table("revenue_clients")
                    .select("*")
                    .eq("operator_id", self.operator_id)
                    .execute()
                )
                if result.data:
                    return [Customer(**r) for r in result.data]
        except Exception:
            pass
        raw = [r for r in self._load_local() if r.get("operator_id") == self.operator_id]
        return [Customer(**r) for r in raw]

    async def _persist(self, customer: Customer) -> None:
        try:
            from factory.integrations.supabase import get_supabase_client
            client = get_supabase_client()
            if client:
                client.table("revenue_clients").upsert(asdict(customer)).execute()
        except Exception:
            pass
        all_data = self._load_local()
        all_data = [r for r in all_data if r.get("id") != customer.id]
        all_data.append(asdict(customer))
        self._save_local(all_data)

    async def get_or_create(
        self, name: str, email: str = "", company: str = "",
    ) -> Customer:
        """Find customer by name or create new."""
        customers = await self._load_all()
        for c in customers:
            if c.name.lower() == name.lower():
                return c
        customer = Customer.create(
            name=name, operator_id=self.operator_id,
            email=email, company=company,
        )
        await self._persist(customer)
        return customer

    async def link_project(self, customer_id: str, project_id: str) -> bool:
        """Associate a project with a customer."""
        customers = await self._load_all()
        for c in customers:
            if c.id == customer_id:
                if project_id not in c.project_ids:
                    c.project_ids.append(project_id)
                    await self._persist(c)
                return True
        return False

    async def add_invoice_total(self, client_name: str, amount: float) -> None:
        """Increment the customer's total invoiced amount."""
        customers = await self._load_all()
        for c in customers:
            if c.name.lower() == client_name.lower():
                c.total_invoiced += amount
                await self._persist(c)
                return

    async def get_all(self) -> list[Customer]:
        """Return all customers sorted by total invoiced."""
        customers = await self._load_all()
        return sorted(customers, key=lambda c: -c.total_invoiced)

    async def format_clients_list(self) -> str:
        """Format /clients response for Telegram."""
        customers = await self.get_all()
        if not customers:
            return "👥 No clients yet.\n\nAdd one with: /invoice [name] [amount] [description]"

        lines = [f"👥 CLIENTS ({len(customers)} total)", ""]
        for c in customers[:15]:
            proj_count = len(c.project_ids)
            lines.append(
                f"• {c.name}"
                + (f" ({c.company})" if c.company else "")
                + f" — ${c.total_invoiced:,.2f}"
                + (f" | {proj_count} project{'s' if proj_count != 1 else ''}" if proj_count else "")
            )
        if len(customers) > 15:
            lines.append(f"...and {len(customers) - 15} more")

        return "\n".join(lines)
