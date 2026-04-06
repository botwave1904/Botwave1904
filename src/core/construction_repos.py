#!/usr/bin/env python3
"""
src/core/construction_repos.py — Construction Domain Repositories
===================================================================
Repository classes for construction-specific tables. These extend
the existing database layer (database.py) and follow the same pattern:
thread-safe, tenant-isolated, SQL kept out of handlers.

All methods require a tenant_id — no cross-tenant data access is possible.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.database import Database


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TenantConfigRepo:
    """Per-tenant trade configuration (rates, personality, specialties)."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, tenant_id: str) -> Optional[Dict]:
        return self.db.query_one("SELECT * FROM tenant_config WHERE tenant_id = ?", (tenant_id,))

    def upsert(self, tenant_id: str, **kwargs) -> None:
        existing = self.get(tenant_id)
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [tenant_id]
            self.db.execute(f"UPDATE tenant_config SET {sets} WHERE tenant_id = ?", tuple(vals))
        else:
            kwargs["tenant_id"] = tenant_id
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" for _ in kwargs)
            self.db.execute(f"INSERT INTO tenant_config ({cols}) VALUES ({placeholders})", tuple(kwargs.values()))

    def get_labor_rates(self, tenant_id: str) -> Dict[str, float]:
        cfg = self.get(tenant_id)
        if not cfg:
            return {"journeyman": 95.0, "apprentice": 55.0, "master": 135.0}
        return {
            "journeyman": cfg.get("labor_rate_journeyman", 95.0),
            "apprentice": cfg.get("labor_rate_apprentice", 55.0),
            "master": cfg.get("labor_rate_master", 135.0),
        }

    def get_markups(self, tenant_id: str) -> Dict[str, float]:
        cfg = self.get(tenant_id)
        if not cfg:
            return {"materials": 20.0, "overhead": 15.0, "profit": 10.0}
        return {
            "materials": cfg.get("markup_materials_pct", 20.0),
            "overhead": cfg.get("markup_overhead_pct", 15.0),
            "profit": cfg.get("profit_margin_pct", 10.0),
        }


class JobRepo:
    """Active jobs / projects per tenant."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, name: str, **kwargs) -> str:
        jid = _uid("job")
        self.db.execute(
            "INSERT INTO jobs (id, tenant_id, customer_id, name, address, description, "
            "job_type, status, bid_amount, start_date, estimated_completion, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (jid, tenant_id, kwargs.get("customer_id"), name, kwargs.get("address"),
             kwargs.get("description"), kwargs.get("job_type"), kwargs.get("status", "bidding"),
             kwargs.get("bid_amount"), kwargs.get("start_date"), kwargs.get("estimated_completion"),
             kwargs.get("notes"))
        )
        return jid

    def get(self, job_id: str, tenant_id: str) -> Optional[Dict]:
        return self.db.query_one("SELECT * FROM jobs WHERE id = ? AND tenant_id = ?", (job_id, tenant_id))

    def list_active(self, tenant_id: str) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM jobs WHERE tenant_id = ? AND status NOT IN ('completed', 'cancelled') "
            "ORDER BY created_at DESC", (tenant_id,))

    def list_all(self, tenant_id: str, limit: int = 50) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM jobs WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit))

    def update_status(self, job_id: str, tenant_id: str, status: str) -> None:
        self.db.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
            (status, _now(), job_id, tenant_id))

    def count(self, tenant_id: str) -> int:
        row = self.db.query_one("SELECT COUNT(*) as cnt FROM jobs WHERE tenant_id = ?", (tenant_id,))
        return row["cnt"] if row else 0


class CrewRepo:
    """Crew members per tenant."""

    def __init__(self, db: Database):
        self.db = db

    def add(self, tenant_id: str, name: str, role: str = "journeyman", **kwargs) -> str:
        cid = _uid("crew")
        self.db.execute(
            "INSERT INTO crew_members (id, tenant_id, name, phone, email, role, hourly_rate, certifications) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, tenant_id, name, kwargs.get("phone"), kwargs.get("email"),
             role, kwargs.get("hourly_rate"), kwargs.get("certifications"))
        )
        return cid

    def list_active(self, tenant_id: str) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM crew_members WHERE tenant_id = ? AND is_active = 1 ORDER BY name",
            (tenant_id,))

    def get(self, crew_id: str, tenant_id: str) -> Optional[Dict]:
        return self.db.query_one(
            "SELECT * FROM crew_members WHERE id = ? AND tenant_id = ?", (crew_id, tenant_id))

    def count(self, tenant_id: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) as cnt FROM crew_members WHERE tenant_id = ? AND is_active = 1", (tenant_id,))
        return row["cnt"] if row else 0


class TimeEntryRepo:
    """Time tracking / payroll entries."""

    def __init__(self, db: Database):
        self.db = db

    def clock_in(self, tenant_id: str, crew_member_id: str, job_id: str = None) -> str:
        tid = _uid("time")
        self.db.execute(
            "INSERT INTO time_entries (id, tenant_id, crew_member_id, job_id, clock_in, status) "
            "VALUES (?, ?, ?, ?, ?, 'open')",
            (tid, tenant_id, crew_member_id, job_id, _now())
        )
        return tid

    def clock_out(self, entry_id: str, tenant_id: str, break_minutes: int = 0) -> Optional[Dict]:
        entry = self.db.query_one(
            "SELECT * FROM time_entries WHERE id = ? AND tenant_id = ? AND status = 'open'",
            (entry_id, tenant_id))
        if not entry:
            return None
        now = _now()
        clock_in = datetime.fromisoformat(entry["clock_in"])
        clock_out = datetime.now(timezone.utc)
        raw_hours = (clock_out - clock_in).total_seconds() / 3600.0
        hours = max(0, raw_hours - (break_minutes / 60.0))
        self.db.execute(
            "UPDATE time_entries SET clock_out = ?, hours_worked = ?, break_minutes = ?, status = 'closed' "
            "WHERE id = ? AND tenant_id = ?",
            (now, round(hours, 2), break_minutes, entry_id, tenant_id))
        return {"entry_id": entry_id, "hours": round(hours, 2)}

    def get_open(self, tenant_id: str, crew_member_id: str) -> Optional[Dict]:
        return self.db.query_one(
            "SELECT * FROM time_entries WHERE tenant_id = ? AND crew_member_id = ? AND status = 'open'",
            (tenant_id, crew_member_id))

    def weekly_summary(self, tenant_id: str, crew_member_id: str) -> Dict:
        rows = self.db.query(
            "SELECT SUM(hours_worked) as total_hours, COUNT(*) as entries "
            "FROM time_entries WHERE tenant_id = ? AND crew_member_id = ? "
            "AND clock_in >= datetime('now', '-7 days') AND status = 'closed'",
            (tenant_id, crew_member_id))
        if rows and rows[0]:
            return {"total_hours": rows[0].get("total_hours") or 0, "entries": rows[0].get("entries") or 0}
        return {"total_hours": 0, "entries": 0}

    def payroll_summary(self, tenant_id: str) -> List[Dict]:
        return self.db.query(
            "SELECT cm.name, cm.role, cm.hourly_rate, "
            "SUM(te.hours_worked) as total_hours, "
            "SUM(te.hours_worked * COALESCE(cm.hourly_rate, 0)) as total_pay "
            "FROM time_entries te JOIN crew_members cm ON te.crew_member_id = cm.id "
            "WHERE te.tenant_id = ? AND te.clock_in >= datetime('now', '-7 days') AND te.status = 'closed' "
            "GROUP BY cm.id ORDER BY cm.name",
            (tenant_id,))


class MaterialRepo:
    """Material inventory and tracking."""

    def __init__(self, db: Database):
        self.db = db

    def add(self, tenant_id: str, name: str, **kwargs) -> str:
        mid = _uid("mat")
        self.db.execute(
            "INSERT INTO materials (id, tenant_id, name, category, unit, unit_cost, "
            "quantity_on_hand, reorder_threshold, preferred_supplier, supplier_sku) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, tenant_id, name, kwargs.get("category"), kwargs.get("unit", "each"),
             kwargs.get("unit_cost"), kwargs.get("quantity_on_hand", 0),
             kwargs.get("reorder_threshold", 0), kwargs.get("preferred_supplier"),
             kwargs.get("supplier_sku"))
        )
        return mid

    def list_all(self, tenant_id: str) -> List[Dict]:
        return self.db.query("SELECT * FROM materials WHERE tenant_id = ? ORDER BY category, name", (tenant_id,))

    def low_stock(self, tenant_id: str) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM materials WHERE tenant_id = ? AND quantity_on_hand <= reorder_threshold "
            "AND reorder_threshold > 0 ORDER BY name", (tenant_id,))

    def use_material(self, tenant_id: str, job_id: str, material_id: str, quantity: float) -> str:
        jmid = _uid("jm")
        mat = self.db.query_one("SELECT * FROM materials WHERE id = ? AND tenant_id = ?", (material_id, tenant_id))
        unit_cost = mat["unit_cost"] if mat else 0
        self.db.execute(
            "INSERT INTO job_materials (id, tenant_id, job_id, material_id, quantity_used, unit_cost_at_use) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (jmid, tenant_id, job_id, material_id, quantity, unit_cost))
        if mat:
            new_qty = max(0, (mat.get("quantity_on_hand") or 0) - quantity)
            self.db.execute("UPDATE materials SET quantity_on_hand = ? WHERE id = ? AND tenant_id = ?",
                            (new_qty, material_id, tenant_id))
        return jmid


class ChangeOrderRepo:
    """Change orders on active jobs."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, job_id: str, description: str, **kwargs) -> str:
        coid = _uid("co")
        self.db.execute(
            "INSERT INTO change_orders (id, tenant_id, job_id, description, reason, "
            "cost_impact, time_impact_days, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed')",
            (coid, tenant_id, job_id, description, kwargs.get("reason"),
             kwargs.get("cost_impact", 0), kwargs.get("time_impact_days", 0))
        )
        return coid

    def list_for_job(self, tenant_id: str, job_id: str) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM change_orders WHERE tenant_id = ? AND job_id = ? ORDER BY created_at DESC",
            (tenant_id, job_id))

    def approve(self, co_id: str, tenant_id: str, approved_by: str) -> None:
        self.db.execute(
            "UPDATE change_orders SET status = 'approved', approved_by = ?, approved_at = ? "
            "WHERE id = ? AND tenant_id = ?",
            (approved_by, _now(), co_id, tenant_id))


class TakeoffRepo:
    """Image/blueprint analysis results."""

    def __init__(self, db: Database):
        self.db = db

    def store(self, tenant_id: str, analysis_text: str, **kwargs) -> str:
        tid = _uid("tkoff")
        self.db.execute(
            "INSERT INTO takeoff_analyses (id, tenant_id, job_id, image_type, original_filename, "
            "analysis_text, extracted_measurements, material_suggestions, "
            "cost_estimate_low, cost_estimate_high, confidence_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, tenant_id, kwargs.get("job_id"), kwargs.get("image_type", "photo"),
             kwargs.get("original_filename"), analysis_text,
             kwargs.get("extracted_measurements"), kwargs.get("material_suggestions"),
             kwargs.get("cost_estimate_low"), kwargs.get("cost_estimate_high"),
             kwargs.get("confidence_score"))
        )
        return tid

    def list_for_job(self, tenant_id: str, job_id: str) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM takeoff_analyses WHERE tenant_id = ? AND job_id = ? ORDER BY created_at DESC",
            (tenant_id, job_id))
