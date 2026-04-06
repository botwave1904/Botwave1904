#!/usr/bin/env python3
"""
src/core/schema_v2.py — Construction Platform Schema Extension
================================================================
Adds construction-specific tables to the existing Botwave database.
Run once after database.py has initialized the base schema.

Tables added:
  - tenant_config     (trade type, bot personality, labor rates)
  - jobs              (active job sites per tenant)
  - crew_members      (workers per tenant)
  - time_entries      (clock in/out per crew member per job)
  - materials         (inventory + ordering per tenant)
  - change_orders     (scope changes on active jobs)
  - takeoff_analyses  (image/blueprint analysis results)

Designed to work alongside existing: tenants, customers, quotes,
appointments, leads, invoices, conversations.
"""

SCHEMA_V2_SQL = """
-- =====================================================================
-- TENANT CONFIG: trade-specific settings per construction company
-- =====================================================================
CREATE TABLE IF NOT EXISTS tenant_config (
    tenant_id TEXT PRIMARY KEY,
    trade_type TEXT NOT NULL DEFAULT 'general',
    company_phone TEXT,
    company_email TEXT,
    company_license TEXT,
    service_area TEXT,
    labor_rate_journeyman REAL DEFAULT 95.0,
    labor_rate_apprentice REAL DEFAULT 55.0,
    labor_rate_master REAL DEFAULT 135.0,
    markup_materials_pct REAL DEFAULT 20.0,
    markup_overhead_pct REAL DEFAULT 15.0,
    profit_margin_pct REAL DEFAULT 10.0,
    minimum_call_out REAL DEFAULT 185.0,
    currency TEXT DEFAULT 'USD',
    bot_personality TEXT DEFAULT 'professional',
    bot_greeting TEXT,
    specialties TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- =====================================================================
-- JOBS: active job sites / projects
-- =====================================================================
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    customer_id TEXT,
    name TEXT NOT NULL,
    address TEXT,
    description TEXT,
    job_type TEXT,
    status TEXT NOT NULL DEFAULT 'bidding',
    bid_amount REAL,
    contract_amount REAL,
    start_date TEXT,
    estimated_completion TEXT,
    actual_completion TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- =====================================================================
-- CREW MEMBERS: workers belonging to a tenant
-- =====================================================================
CREATE TABLE IF NOT EXISTS crew_members (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'journeyman',
    hourly_rate REAL,
    is_active INTEGER DEFAULT 1,
    certifications TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- =====================================================================
-- TIME ENTRIES: clock in/out per crew member per job
-- =====================================================================
CREATE TABLE IF NOT EXISTS time_entries (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    crew_member_id TEXT NOT NULL,
    job_id TEXT,
    clock_in TIMESTAMP NOT NULL,
    clock_out TIMESTAMP,
    hours_worked REAL,
    break_minutes INTEGER DEFAULT 0,
    notes TEXT,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (crew_member_id) REFERENCES crew_members(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- =====================================================================
-- MATERIALS: inventory + order tracking
-- =====================================================================
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    unit TEXT DEFAULT 'each',
    unit_cost REAL,
    quantity_on_hand REAL DEFAULT 0,
    reorder_threshold REAL DEFAULT 0,
    preferred_supplier TEXT,
    supplier_sku TEXT,
    last_ordered TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- =====================================================================
-- JOB MATERIALS: materials allocated to specific jobs
-- =====================================================================
CREATE TABLE IF NOT EXISTS job_materials (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    quantity_used REAL NOT NULL,
    unit_cost_at_use REAL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (material_id) REFERENCES materials(id)
);

-- =====================================================================
-- CHANGE ORDERS: scope changes on active jobs
-- =====================================================================
CREATE TABLE IF NOT EXISTS change_orders (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    description TEXT NOT NULL,
    reason TEXT,
    cost_impact REAL DEFAULT 0,
    time_impact_days INTEGER DEFAULT 0,
    status TEXT DEFAULT 'proposed',
    approved_by TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- =====================================================================
-- TAKEOFF ANALYSES: image/blueprint analysis results
-- =====================================================================
CREATE TABLE IF NOT EXISTS takeoff_analyses (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT,
    image_type TEXT DEFAULT 'photo',
    original_filename TEXT,
    analysis_text TEXT,
    extracted_measurements TEXT,
    material_suggestions TEXT,
    cost_estimate_low REAL,
    cost_estimate_high REAL,
    confidence_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- Add trade_type column to tenants if not exists
-- (SQLite doesn't support IF NOT EXISTS for ALTER TABLE,
-- so we handle this in Python)
"""


def apply_v2_schema(db) -> None:
    """Apply construction schema extension to existing database."""
    with db.transaction() as conn:
        conn.executescript(SCHEMA_V2_SQL)

        # Add trade_type to tenants table if missing
        cursor = conn.execute("PRAGMA table_info(tenants)")
        columns = {row[1] for row in cursor.fetchall()}
        if "trade_type" not in columns:
            conn.execute("ALTER TABLE tenants ADD COLUMN trade_type TEXT DEFAULT 'general'")

    print("[schema_v2] Construction tables applied successfully.")
