#!/usr/bin/env python3
"""
src/core/database.py — Botwave Database Layer
===============================================
Thread-safe SQLite connection manager with schema migrations,
query helpers, and connection pooling for the Flask dashboard.

For production: swap SQLite for PostgreSQL by changing the
DATABASE_URL environment variable and installing psycopg2.
"""

import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent.parent / "data" / "botwave.db"))


class Database:
    """Thread-safe SQLite database manager."""

    _local = threading.local()

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def transaction(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid

    def _init_schema(self):
        with self.transaction() as conn:
            conn.executescript(SCHEMA_SQL)


SCHEMA_SQL = """
-- Tenants (multi-tenant support)
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    plan TEXT NOT NULL DEFAULT 'starter',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'trial',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Customers (end-clients of each tenant)
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    telegram_id TEXT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- Quotes
CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    customer_id TEXT,
    customer_name TEXT NOT NULL,
    service_type TEXT,
    description TEXT,
    price_low REAL,
    price_high REAL,
    estimated_hours REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Appointments
CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    customer_id TEXT,
    customer_name TEXT NOT NULL,
    phone TEXT,
    service_type TEXT,
    scheduled_date TEXT,
    scheduled_time TEXT,
    address TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Leads (from website forms, bot interactions)
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    source TEXT NOT NULL DEFAULT 'website',
    name TEXT,
    email TEXT,
    phone TEXT,
    company TEXT,
    industry TEXT,
    message TEXT,
    budget TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Invoices
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    customer_id TEXT,
    quote_id TEXT,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    stripe_payment_intent TEXT,
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (quote_id) REFERENCES quotes(id)
);

-- Bot conversations (for analytics)
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    user_id TEXT,
    user_name TEXT,
    channel TEXT DEFAULT 'telegram',
    message TEXT,
    bot_response TEXT,
    intent TEXT,
    sentiment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default tenant if not exists
INSERT OR IGNORE INTO tenants (id, name, plan, status)
VALUES ('default', 'Default Tenant', 'professional', 'active');
"""


# ---------------------------------------------------------------------------
# Repository helpers (keep SQL out of route handlers)
# ---------------------------------------------------------------------------
class CustomerRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, name: str, **kwargs) -> str:
        cid = f"cust_{uuid.uuid4().hex[:12]}"
        self.db.execute(
            "INSERT INTO customers (id, tenant_id, name, phone, email, address, telegram_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, tenant_id, name, kwargs.get("phone"), kwargs.get("email"),
             kwargs.get("address"), kwargs.get("telegram_id"))
        )
        return cid

    def get(self, customer_id: str) -> Optional[Dict]:
        return self.db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))

    def list_all(self, tenant_id: str = "default", limit: int = 100) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM customers WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit)
        )

    def count(self, tenant_id: str = "default") -> int:
        row = self.db.query_one("SELECT COUNT(*) as cnt FROM customers WHERE tenant_id = ?", (tenant_id,))
        return row["cnt"] if row else 0


class QuoteRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, customer_name: str, service_type: str,
               description: str, price_low: float, price_high: float, **kwargs) -> str:
        qid = f"qt_{uuid.uuid4().hex[:12]}"
        self.db.execute(
            "INSERT INTO quotes (id, tenant_id, customer_name, service_type, description, "
            "price_low, price_high, estimated_hours, customer_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, tenant_id, customer_name, service_type, description,
             price_low, price_high, kwargs.get("estimated_hours"), kwargs.get("customer_id"))
        )
        return qid

    def list_all(self, tenant_id: str = "default", status: str = None, limit: int = 100) -> List[Dict]:
        if status:
            return self.db.query(
                "SELECT * FROM quotes WHERE tenant_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, status, limit)
            )
        return self.db.query(
            "SELECT * FROM quotes WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit)
        )

    def count(self, tenant_id: str = "default") -> int:
        row = self.db.query_one("SELECT COUNT(*) as cnt FROM quotes WHERE tenant_id = ?", (tenant_id,))
        return row["cnt"] if row else 0

    def update_status(self, quote_id: str, status: str):
        self.db.execute("UPDATE quotes SET status = ? WHERE id = ?", (status, quote_id))


class AppointmentRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, customer_name: str, service_type: str,
               scheduled_date: str, scheduled_time: str, **kwargs) -> str:
        aid = f"apt_{uuid.uuid4().hex[:12]}"
        self.db.execute(
            "INSERT INTO appointments (id, tenant_id, customer_name, service_type, "
            "scheduled_date, scheduled_time, phone, address, notes, customer_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (aid, tenant_id, customer_name, service_type, scheduled_date, scheduled_time,
             kwargs.get("phone"), kwargs.get("address"), kwargs.get("notes"), kwargs.get("customer_id"))
        )
        return aid

    def list_all(self, tenant_id: str = "default", limit: int = 100) -> List[Dict]:
        return self.db.query(
            "SELECT * FROM appointments WHERE tenant_id = ? ORDER BY scheduled_date DESC LIMIT ?",
            (tenant_id, limit)
        )

    def list_upcoming(self, tenant_id: str = "default", limit: int = 20) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.db.query(
            "SELECT * FROM appointments WHERE tenant_id = ? AND scheduled_date >= ? "
            "AND status = 'scheduled' ORDER BY scheduled_date, scheduled_time LIMIT ?",
            (tenant_id, today, limit)
        )

    def count(self, tenant_id: str = "default") -> int:
        row = self.db.query_one("SELECT COUNT(*) as cnt FROM appointments WHERE tenant_id = ?", (tenant_id,))
        return row["cnt"] if row else 0


class LeadRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, source: str = "website", **kwargs) -> str:
        lid = f"lead_{uuid.uuid4().hex[:12]}"
        self.db.execute(
            "INSERT INTO leads (id, tenant_id, source, name, email, phone, company, industry, message, budget) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lid, kwargs.get("tenant_id", "default"), source, kwargs.get("name"), kwargs.get("email"),
             kwargs.get("phone"), kwargs.get("company"), kwargs.get("industry"),
             kwargs.get("message"), kwargs.get("budget"))
        )
        return lid

    def list_all(self, tenant_id: str = "default", status: str = None, limit: int = 100) -> List[Dict]:
        if status:
            return self.db.query(
                "SELECT * FROM leads WHERE tenant_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, status, limit)
            )
        return self.db.query(
            "SELECT * FROM leads WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit)
        )

    def count(self, tenant_id: str = "default") -> int:
        row = self.db.query_one("SELECT COUNT(*) as cnt FROM leads WHERE tenant_id = ?", (tenant_id,))
        return row["cnt"] if row else 0


class InvoiceRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, customer_id: str, amount: float, **kwargs) -> str:
        iid = f"inv_{uuid.uuid4().hex[:12]}"
        self.db.execute(
            "INSERT INTO invoices (id, tenant_id, customer_id, quote_id, amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (iid, tenant_id, customer_id, kwargs.get("quote_id"), amount, kwargs.get("status", "draft"))
        )
        return iid

    def revenue_total(self, tenant_id: str = "default") -> float:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(amount), 0) as total FROM invoices WHERE tenant_id = ? AND status = 'paid'",
            (tenant_id,)
        )
        return row["total"] if row else 0.0


# Singleton for convenience
_db_instance: Optional[Database] = None

def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
