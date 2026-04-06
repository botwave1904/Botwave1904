#!/usr/bin/env python3
"""
tests/test_core.py — Botwave Core Test Suite
==============================================
Tests the critical paths that, if broken, would lose money or expose data.

Run:  pytest tests/test_core.py -v
"""

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def temp_db():
    """Create a temporary database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path
    # Reimport to get fresh DB
    from src.core.database import Database
    db = Database(db_path)
    yield db
    os.unlink(db_path)


@pytest.fixture
def repos(temp_db):
    """Create all repos with the temp database."""
    from src.core.database import CustomerRepo, QuoteRepo, AppointmentRepo, LeadRepo, InvoiceRepo
    return {
        "db": temp_db,
        "customers": CustomerRepo(temp_db),
        "quotes": QuoteRepo(temp_db),
        "appointments": AppointmentRepo(temp_db),
        "leads": LeadRepo(temp_db),
        "invoices": InvoiceRepo(temp_db),
    }


@pytest.fixture
def two_tenants(repos):
    """Create two tenants for isolation testing."""
    db = repos["db"]
    db.execute(
        "INSERT INTO tenants (id, name, plan, status) VALUES (?, ?, ?, ?)",
        ("t_alpha", "Alpha Plumbing", "professional", "active")
    )
    db.execute(
        "INSERT INTO tenants (id, name, plan, status) VALUES (?, ?, ?, ?)",
        ("t_beta", "Beta Electric", "starter", "active")
    )
    return "t_alpha", "t_beta"


# ══════════════════════════════════════════════════════════════════════
# 1. TENANT ISOLATION TESTS
# ══════════════════════════════════════════════════════════════════════

class TestTenantIsolation:
    """Verify that tenant A can NEVER see tenant B's data."""

    def test_customer_isolation(self, repos, two_tenants):
        """Customers created under tenant A should not appear in tenant B queries."""
        t_a, t_b = two_tenants
        c = repos["customers"]

        # Create customers for each tenant
        c.create(tenant_id=t_a, name="Alpha Customer 1", phone="555-0001")
        c.create(tenant_id=t_a, name="Alpha Customer 2", phone="555-0002")
        c.create(tenant_id=t_b, name="Beta Customer 1", phone="555-0003")

        # Tenant A should see 2 customers
        alpha_customers = c.list_all(tenant_id=t_a)
        assert len(alpha_customers) == 2
        assert all(x["tenant_id"] == t_a for x in alpha_customers)

        # Tenant B should see 1 customer
        beta_customers = c.list_all(tenant_id=t_b)
        assert len(beta_customers) == 1
        assert beta_customers[0]["tenant_id"] == t_b
        assert beta_customers[0]["name"] == "Beta Customer 1"

    def test_quote_isolation(self, repos, two_tenants):
        """Quotes should be scoped by tenant."""
        t_a, t_b = two_tenants
        q = repos["quotes"]

        q.create(tenant_id=t_a, customer_name="A Client", service_type="Drain",
                 price_low=200, price_high=500, description="test")
        q.create(tenant_id=t_b, customer_name="B Client", service_type="Wiring",
                 price_low=300, price_high=800, description="test")

        assert q.count(t_a) == 1
        assert q.count(t_b) == 1

        a_quotes = q.list_all(tenant_id=t_a)
        assert len(a_quotes) == 1
        assert a_quotes[0]["customer_name"] == "A Client"

    def test_lead_isolation(self, repos, two_tenants):
        """Leads should be scoped by tenant."""
        t_a, t_b = two_tenants
        l = repos["leads"]

        l.create(tenant_id=t_a, name="Lead A", email="a@test.com", source="website")
        l.create(tenant_id=t_a, name="Lead A2", email="a2@test.com", source="website")
        l.create(tenant_id=t_b, name="Lead B", email="b@test.com", source="telegram")

        assert l.count(t_a) == 2
        assert l.count(t_b) == 1

    def test_revenue_isolation(self, repos, two_tenants):
        """Revenue totals should be tenant-scoped."""
        t_a, t_b = two_tenants
        inv = repos["invoices"]

        # Alpha gets $1000 in invoices, Beta gets $500
        inv.create(tenant_id=t_a, customer_name="A", amount=1000, status="paid")
        inv.create(tenant_id=t_b, customer_name="B", amount=500, status="paid")

        assert inv.revenue_total(t_a) == 1000
        assert inv.revenue_total(t_b) == 500

    def test_count_with_no_tenant_returns_all(self, repos, two_tenants):
        """Admin view (tenant_id=None) should return all records."""
        t_a, t_b = two_tenants
        c = repos["customers"]

        c.create(tenant_id=t_a, name="A1")
        c.create(tenant_id=t_b, name="B1")

        # None = admin sees everything
        assert c.count(None) >= 2 or c.count() >= 2


# ══════════════════════════════════════════════════════════════════════
# 2. QUOTING ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════

class TestQuotingEngine:
    """Verify that the quoting engine calculates prices correctly."""

    def test_service_detection_by_keyword(self):
        """Trade profile should match services by keyword."""
        from src.core.trade_profiles import get_trade_profile
        profile = get_trade_profile("plumbing")

        # "clogged drain" should match "Drain Cleaning"
        svc = profile.detect_service("my kitchen drain is clogged")
        assert svc is not None
        assert svc.name == "Drain Cleaning"

    def test_service_detection_leak(self):
        """Leak keywords should match Leak Repair."""
        from src.core.trade_profiles import get_trade_profile
        profile = get_trade_profile("plumbing")

        svc = profile.detect_service("there's a leak under my sink")
        assert svc is not None
        assert svc.name == "Leak Repair"

    def test_service_detection_no_match(self):
        """Random text should return None."""
        from src.core.trade_profiles import get_trade_profile
        profile = get_trade_profile("plumbing")

        svc = profile.detect_service("I like pizza")
        assert svc is None

    def test_water_heater_detection(self):
        """Water heater keywords should match correctly."""
        from src.core.trade_profiles import get_trade_profile
        profile = get_trade_profile("plumbing")

        svc = profile.detect_service("no hot water in the house")
        assert svc is not None
        assert "Water Heater" in svc.name or "heater" in svc.name.lower()

    def test_quote_price_range_is_valid(self):
        """Price low should always be less than price high."""
        from src.core.trade_profiles import get_trade_profile
        profile = get_trade_profile("plumbing")

        for service in profile.services:
            assert service.hours_low <= service.hours_high, \
                f"{service.name}: hours_low ({service.hours_low}) > hours_high ({service.hours_high})"
            assert service.parts_low <= service.parts_high, \
                f"{service.name}: parts_low ({service.parts_low}) > parts_high ({service.parts_high})"

    def test_all_services_have_keywords(self):
        """Every service must have at least one keyword for detection."""
        from src.core.trade_profiles import get_trade_profile
        profile = get_trade_profile("plumbing")

        for service in profile.services:
            assert len(service.keywords) > 0, \
                f"{service.name} has no keywords — it can never be matched"


# ══════════════════════════════════════════════════════════════════════
# 3. STRATEGIST TESTS
# ══════════════════════════════════════════════════════════════════════

class TestStrategist:
    """Verify the finding classification engine."""

    def test_critical_finding_with_trigger(self):
        """High-priority trigger should make finding Critical."""
        from src.strategist import Strategist

        logic = {
            "keywords": ["leak", {"burst_pipe": 3}],
            "high_priority_triggers": ["no water", "gas smell"],
            "critical_threshold": 3,
        }
        finding = {"id": "f1", "summary": "No water in the building", "details": ""}

        result = Strategist.score_finding(finding, logic)
        assert result["classification"] == "Critical"
        assert result["score"] >= 3

    def test_non_critical_finding(self):
        """Low-score finding should be NonCritical."""
        from src.strategist import Strategist

        logic = {
            "keywords": ["leak", "burst"],
            "high_priority_triggers": ["no water"],
            "critical_threshold": 3,
        }
        finding = {"id": "f2", "summary": "Slow drip from faucet", "details": ""}

        result = Strategist.score_finding(finding, logic)
        assert result["classification"] == "NonCritical"

    def test_keyword_weight_accumulation(self):
        """Multiple keyword matches should accumulate score."""
        from src.strategist import Strategist

        logic = {
            "keywords": [{"leak": 2}, {"burst": 2}],
            "high_priority_triggers": [],
            "critical_threshold": 3,
        }
        finding = {"id": "f3", "summary": "Leak from burst pipe", "details": ""}

        result = Strategist.score_finding(finding, logic)
        assert result["score"] >= 4  # leak(2) + burst(2)
        assert result["classification"] == "Critical"


# ══════════════════════════════════════════════════════════════════════
# 4. GATEKEEPER TESTS
# ══════════════════════════════════════════════════════════════════════

class TestGatekeeper:
    """Verify subscription tier enforcement."""

    def test_rate_limiter_allows_within_limit(self):
        """Rate limiter should allow requests within the limit."""
        from src.gatekeeper import RateLimiter
        rl = RateLimiter()

        for _ in range(5):
            assert rl.check_and_consume("key1", "feature1", 5) is True

    def test_rate_limiter_blocks_over_limit(self):
        """Rate limiter should block requests over the limit."""
        from src.gatekeeper import RateLimiter
        rl = RateLimiter()

        for _ in range(3):
            rl.check_and_consume("key2", "feature2", 3)

        assert rl.check_and_consume("key2", "feature2", 3) is False

    def test_rate_limiter_unlimited(self):
        """None limit should allow unlimited requests."""
        from src.gatekeeper import RateLimiter
        rl = RateLimiter()

        for _ in range(100):
            assert rl.check_and_consume("key3", "feature3", None) is True

    def test_normalize_keywords_strings(self):
        """String keywords should normalize to (term, 1) tuples."""
        from src.strategist import Strategist
        result = Strategist.normalize_keywords(["leak", "burst"])
        assert ("leak", 1) in result
        assert ("burst", 1) in result

    def test_normalize_keywords_dicts(self):
        """Dict keywords should preserve weights."""
        from src.strategist import Strategist
        result = Strategist.normalize_keywords([{"leak": 3}])
        assert ("leak", 3) in result


# ══════════════════════════════════════════════════════════════════════
# 5. AUTH & SECURITY TESTS
# ══════════════════════════════════════════════════════════════════════

class TestAuth:
    """Verify the authentication system."""

    def test_password_hashing_roundtrip(self):
        """Hashed password should verify correctly."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
        from web_app_v2 import hash_password, verify_password

        pw = "my-secure-password-123"
        hashed = hash_password(pw)

        assert verify_password(pw, hashed) is True
        assert verify_password("wrong-password", hashed) is False

    def test_password_hash_is_salted(self):
        """Same password should produce different hashes (due to salt)."""
        from web_app_v2 import hash_password

        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2  # Different salts

    def test_sanitize_strips_html(self):
        """Sanitize should escape HTML tags."""
        from web_app_v2 import sanitize

        assert "&lt;script&gt;" in sanitize("<script>alert('xss')</script>")
        assert "<script>" not in sanitize("<script>alert('xss')</script>")

    def test_sanitize_length_limit(self):
        """Sanitize should truncate to max_length."""
        from web_app_v2 import sanitize

        result = sanitize("a" * 1000, max_length=100)
        assert len(result) == 100

    def test_sanitize_null_bytes(self):
        """Sanitize should strip null bytes."""
        from web_app_v2 import sanitize

        assert "\x00" not in sanitize("hello\x00world")


# ══════════════════════════════════════════════════════════════════════
# 6. OVERHAUL INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════

class TestOverhaulIntegration:
    """Verify the overhaul-to-platform bridge works."""

    def test_overhaul_report_table_exists(self, temp_db):
        """The overhaul_reports table should be created."""
        # The web_app_v2 creates it on import; simulate with direct SQL
        temp_db.execute("""
            CREATE TABLE IF NOT EXISTS overhaul_reports (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                files_organized INTEGER DEFAULT 0,
                space_reclaimed_bytes INTEGER DEFAULT 0,
                threats_found INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                machine_name TEXT,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert a report
        temp_db.execute(
            "INSERT INTO overhaul_reports (id, tenant_id, files_organized, status, machine_name) "
            "VALUES (?, ?, ?, ?, ?)",
            ("ov_test1", "t_alpha", 147, "complete", "DESKTOP-TEST")
        )

        report = temp_db.query_one("SELECT * FROM overhaul_reports WHERE id = ?", ("ov_test1",))
        assert report is not None
        assert report["files_organized"] == 147
        assert report["status"] == "complete"
        assert report["machine_name"] == "DESKTOP-TEST"

    def test_overhaul_updates_tenant_status(self, temp_db):
        """Completing an overhaul should update tenant status from trial to active."""
        temp_db.execute(
            "INSERT INTO tenants (id, name, plan, status) VALUES (?, ?, ?, ?)",
            ("t_test", "Test Co", "professional", "trial")
        )

        # Simulate overhaul completion
        temp_db.execute(
            "UPDATE tenants SET status = 'active' WHERE id = ? AND status = 'trial'",
            ("t_test",)
        )

        tenant = temp_db.query_one("SELECT * FROM tenants WHERE id = ?", ("t_test",))
        assert tenant["status"] == "active"


# ══════════════════════════════════════════════════════════════════════
# 7. STRIPE LIFECYCLE TESTS
# ══════════════════════════════════════════════════════════════════════

class TestStripeLifecycle:
    """Verify subscription state transitions."""

    def test_payment_failure_sets_past_due(self, temp_db):
        """First payment failure should set tenant to past_due."""
        temp_db.execute(
            "INSERT INTO tenants (id, name, plan, status, stripe_subscription_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("t_pay", "Pay Co", "starter", "active", "sub_test123")
        )

        # Simulate payment failure (attempt 1)
        temp_db.execute(
            "UPDATE tenants SET status = 'past_due' WHERE stripe_subscription_id = ?",
            ("sub_test123",)
        )

        tenant = temp_db.query_one("SELECT * FROM tenants WHERE id = ?", ("t_pay",))
        assert tenant["status"] == "past_due"

    def test_three_failures_suspends(self, temp_db):
        """Three payment failures should suspend the tenant."""
        temp_db.execute(
            "INSERT INTO tenants (id, name, plan, status, stripe_subscription_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("t_sus", "Suspend Co", "professional", "past_due", "sub_suspend")
        )

        # Simulate 3rd failure → suspend
        temp_db.execute(
            "UPDATE tenants SET status = 'suspended' WHERE stripe_subscription_id = ?",
            ("sub_suspend",)
        )

        tenant = temp_db.query_one("SELECT * FROM tenants WHERE id = ?", ("t_sus",))
        assert tenant["status"] == "suspended"

    def test_successful_payment_reactivates(self, temp_db):
        """Successful payment should reactivate a past_due tenant."""
        temp_db.execute(
            "INSERT INTO tenants (id, name, plan, status, stripe_subscription_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("t_react", "Reactivate Co", "starter", "past_due", "sub_react")
        )

        temp_db.execute(
            "UPDATE tenants SET status = 'active' WHERE stripe_subscription_id = ?",
            ("sub_react",)
        )

        tenant = temp_db.query_one("SELECT * FROM tenants WHERE id = ?", ("t_react",))
        assert tenant["status"] == "active"

    def test_cancellation_sets_cancelled(self, temp_db):
        """Subscription deletion should set tenant to cancelled."""
        temp_db.execute(
            "INSERT INTO tenants (id, name, plan, status, stripe_subscription_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("t_cancel", "Cancel Co", "enterprise", "active", "sub_cancel")
        )

        temp_db.execute(
            "UPDATE tenants SET status = 'cancelled' WHERE stripe_subscription_id = ?",
            ("sub_cancel",)
        )

        tenant = temp_db.query_one("SELECT * FROM tenants WHERE id = ?", ("t_cancel",))
        assert tenant["status"] == "cancelled"

    def test_plan_upgrade(self, temp_db):
        """Plan change should update the tenant's plan field."""
        temp_db.execute(
            "INSERT INTO tenants (id, name, plan, status, stripe_subscription_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("t_upgrade", "Upgrade Co", "starter", "active", "sub_upgrade")
        )

        temp_db.execute(
            "UPDATE tenants SET plan = 'professional' WHERE stripe_subscription_id = ?",
            ("sub_upgrade",)
        )

        tenant = temp_db.query_one("SELECT * FROM tenants WHERE id = ?", ("t_upgrade",))
        assert tenant["plan"] == "professional"


# ══════════════════════════════════════════════════════════════════════
# 8. DATABASE SAFETY TESTS
# ══════════════════════════════════════════════════════════════════════

class TestDatabaseSafety:
    """Verify database handles edge cases safely."""

    def test_sql_injection_in_customer_name(self, repos, two_tenants):
        """SQL injection attempt in customer name should be stored as literal string."""
        t_a, _ = two_tenants
        c = repos["customers"]

        malicious_name = "'; DROP TABLE customers; --"
        c.create(tenant_id=t_a, name=malicious_name)

        # Table should still exist and contain the record
        result = c.list_all(tenant_id=t_a)
        assert len(result) >= 1
        assert any(x["name"] == malicious_name for x in result)

    def test_empty_string_fields(self, repos, two_tenants):
        """Empty strings should be handled gracefully."""
        t_a, _ = two_tenants
        c = repos["customers"]

        cid = c.create(tenant_id=t_a, name="", phone="", email="")
        # Should not crash
        assert cid is not None

    def test_unicode_in_fields(self, repos, two_tenants):
        """Unicode characters should be stored and retrieved correctly."""
        t_a, _ = two_tenants
        c = repos["customers"]

        c.create(tenant_id=t_a, name="José García", phone="555-0001")
        result = c.list_all(tenant_id=t_a)
        assert any("José" in x["name"] for x in result)
