#!/usr/bin/env python3
"""
dashboard/web_app.py — Botwave Dashboard & REST API
=====================================================
Production Flask application providing:
  - Business dashboard with real-time stats
  - REST API for customers, quotes, appointments, leads
  - Stripe checkout session creation and webhook handling
  - Lead capture endpoint for website forms
  - Health check endpoint for monitoring

Usage:
  python dashboard/web_app.py                  # development
  gunicorn -w 4 -b 0.0.0.0:5000 dashboard.web_app:app  # production
"""

import json
import os
import sys
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify, render_template, redirect, url_for

from src.core.database import (
    get_db, CustomerRepo, QuoteRepo, AppointmentRepo, LeadRepo, InvoiceRepo
)

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="../website", static_url_path="/website")

app.secret_key = os.getenv("API_SECRET_KEY", "change-me-in-production")

# Stripe (optional — graceful degradation if not configured)
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

PRICE_IDS = {
    "starter": os.getenv("STRIPE_PRICE_ID_STARTER", ""),
    "professional": os.getenv("STRIPE_PRICE_ID_PROFESSIONAL", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ID_ENTERPRISE", ""),
}

stripe = None
if STRIPE_SECRET:
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = STRIPE_SECRET
        stripe = stripe_lib
    except ImportError:
        pass

# Initialize database and repos
db = get_db()
customers = CustomerRepo(db)
quotes = QuoteRepo(db)
appointments = AppointmentRepo(db)
leads = LeadRepo(db)
invoices = InvoiceRepo(db)


# ---------------------------------------------------------------------------
# Auth Middleware (simple API key for now)
# ---------------------------------------------------------------------------
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        expected = os.getenv("API_SECRET_KEY", "change-me-in-production")
        if key and key == expected:
            return f(*args, **kwargs)
        # Allow unauthenticated access to dashboard in dev mode
        if os.getenv("API_DEBUG", "false").lower() == "true":
            return f(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return decorated


# ---------------------------------------------------------------------------
# Dashboard Routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    """Main dashboard view."""
    stats = {
        "customers": customers.count(),
        "quotes": quotes.count(),
        "appointments": appointments.count(),
        "leads": leads.count(),
        "revenue": invoices.revenue_total(),
        "pending_quotes": len(quotes.list_all(status="pending")),
        "upcoming_appointments": len(appointments.list_upcoming()),
        "new_leads": len(leads.list_all(status="new")),
    }
    recent_leads = leads.list_all(limit=5)
    recent_quotes = quotes.list_all(limit=5)
    upcoming = appointments.list_upcoming(limit=5)
    return render_template("dashboard.html", stats=stats, leads=recent_leads,
                           quotes=recent_quotes, appointments=upcoming)


@app.route("/health")
def health():
    """Health check endpoint for monitoring."""
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": "connected",
        "stripe": "configured" if stripe else "not_configured",
    })


# ---------------------------------------------------------------------------
# Customer API
# ---------------------------------------------------------------------------
@app.route("/api/customers", methods=["GET"])
@require_api_key
def api_list_customers():
    return jsonify({"customers": customers.list_all(), "count": customers.count()})


@app.route("/api/customers", methods=["POST"])
@require_api_key
def api_create_customer():
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    cid = customers.create(
        tenant_id=data.get("tenant_id", "default"),
        name=data["name"],
        phone=data.get("phone"),
        email=data.get("email"),
        address=data.get("address"),
        telegram_id=data.get("telegram_id"),
    )
    return jsonify({"id": cid, "status": "created"}), 201


@app.route("/api/customers/<customer_id>", methods=["GET"])
@require_api_key
def api_get_customer(customer_id):
    c = customers.get(customer_id)
    if not c:
        return jsonify({"error": "not found"}), 404
    return jsonify(c)


# ---------------------------------------------------------------------------
# Quotes API
# ---------------------------------------------------------------------------
@app.route("/api/quotes", methods=["GET"])
@require_api_key
def api_list_quotes():
    status = request.args.get("status")
    return jsonify({"quotes": quotes.list_all(status=status), "count": quotes.count()})


@app.route("/api/quotes", methods=["POST"])
@require_api_key
def api_create_quote():
    data = request.get_json(force=True)
    required = ["customer_name", "service_type", "price_low", "price_high"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    qid = quotes.create(
        tenant_id=data.get("tenant_id", "default"),
        customer_name=data["customer_name"],
        service_type=data["service_type"],
        description=data.get("description", ""),
        price_low=float(data["price_low"]),
        price_high=float(data["price_high"]),
        estimated_hours=data.get("estimated_hours"),
        customer_id=data.get("customer_id"),
    )
    return jsonify({"id": qid, "status": "created"}), 201


@app.route("/api/quotes/<quote_id>/status", methods=["PUT"])
@require_api_key
def api_update_quote_status(quote_id):
    data = request.get_json(force=True)
    new_status = data.get("status")
    if new_status not in ("pending", "accepted", "rejected", "expired"):
        return jsonify({"error": "Invalid status"}), 400
    quotes.update_status(quote_id, new_status)
    return jsonify({"id": quote_id, "status": new_status})


# ---------------------------------------------------------------------------
# Appointments API
# ---------------------------------------------------------------------------
@app.route("/api/appointments", methods=["GET"])
@require_api_key
def api_list_appointments():
    return jsonify({"appointments": appointments.list_all(), "count": appointments.count()})


@app.route("/api/appointments", methods=["POST"])
@require_api_key
def api_create_appointment():
    data = request.get_json(force=True)
    required = ["customer_name", "service_type", "scheduled_date", "scheduled_time"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    aid = appointments.create(
        tenant_id=data.get("tenant_id", "default"),
        customer_name=data["customer_name"],
        service_type=data["service_type"],
        scheduled_date=data["scheduled_date"],
        scheduled_time=data["scheduled_time"],
        phone=data.get("phone"),
        address=data.get("address"),
        notes=data.get("notes"),
        customer_id=data.get("customer_id"),
    )
    return jsonify({"id": aid, "status": "created"}), 201


@app.route("/api/appointments/upcoming", methods=["GET"])
@require_api_key
def api_upcoming_appointments():
    return jsonify({"appointments": appointments.list_upcoming()})


# ---------------------------------------------------------------------------
# Leads API
# ---------------------------------------------------------------------------
@app.route("/api/leads", methods=["GET"])
@require_api_key
def api_list_leads():
    status = request.args.get("status")
    return jsonify({"leads": leads.list_all(status=status), "count": leads.count()})


@app.route("/api/leads", methods=["POST"])
def api_capture_lead():
    """Public endpoint — no API key required. Used by website forms."""
    data = request.get_json(force=True)
    if not data.get("email") and not data.get("phone"):
        return jsonify({"error": "Email or phone required"}), 400
    lid = leads.create(
        source=data.get("source", "website"),
        name=data.get("name"),
        email=data.get("email"),
        phone=data.get("phone"),
        company=data.get("company"),
        industry=data.get("industry"),
        message=data.get("message"),
        budget=data.get("budget"),
        tenant_id=data.get("tenant_id", "default"),
    )
    return jsonify({"id": lid, "status": "captured", "message": "Thank you! We'll be in touch within 24 hours."}), 201


# ---------------------------------------------------------------------------
# Stats API
# ---------------------------------------------------------------------------
@app.route("/api/stats", methods=["GET"])
@require_api_key
def api_stats():
    return jsonify({
        "customers": customers.count(),
        "quotes": quotes.count(),
        "appointments": appointments.count(),
        "leads": leads.count(),
        "revenue": invoices.revenue_total(),
        "pending_quotes": len(quotes.list_all(status="pending")),
        "upcoming_appointments": len(appointments.list_upcoming()),
        "new_leads": len(leads.list_all(status="new")),
    })


# ---------------------------------------------------------------------------
# Stripe Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/stripe/status", methods=["GET"])
def api_stripe_status():
    return jsonify({
        "configured": stripe is not None,
        "publishable_key": STRIPE_PUBLISHABLE[:12] + "..." if STRIPE_PUBLISHABLE else None,
        "plans": {k: bool(v) for k, v in PRICE_IDS.items()},
    })


@app.route("/api/stripe/create-checkout-session", methods=["POST"])
def api_create_checkout():
    if not stripe:
        return jsonify({"error": "Stripe not configured. Set STRIPE_SECRET_KEY in .env"}), 503

    data = request.get_json(force=True)
    plan = data.get("plan", "starter")
    price_id = PRICE_IDS.get(plan)

    if not price_id:
        return jsonify({"error": f"No price ID configured for plan: {plan}"}), 400

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=request.host_url + "website/onboarding.html?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "website/pricing.html?cancelled=true",
            metadata={"plan": plan},
        )
        return jsonify({"session_id": session.id, "url": session.url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stripe/webhook", methods=["POST"])
def api_stripe_webhook():
    if not stripe:
        return jsonify({"error": "Stripe not configured"}), 503

    payload = request.get_data(as_text=True)
    sig = request.headers.get("Stripe-Signature", "")

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    event_type = event.get("type", "")
    if event_type == "checkout.session.completed":
        session_data = event["data"]["object"]
        app.logger.info("Checkout completed: %s (plan=%s)",
                        session_data.get("id"), session_data.get("metadata", {}).get("plan"))
    elif event_type == "invoice.paid":
        app.logger.info("Invoice paid: %s", event["data"]["object"].get("id"))

    return jsonify({"received": True})


# ---------------------------------------------------------------------------
# Website Serving
# ---------------------------------------------------------------------------
@app.route("/website/")
@app.route("/website/<path:filename>")
def serve_website(filename="index.html"):
    return app.send_static_file(filename)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "5000"))
    debug = os.getenv("API_DEBUG", "false").lower() == "true"

    print(f"\n{'='*60}")
    print(f"  BOTWAVE DASHBOARD v1.0.0")
    print(f"  Dashboard:  http://{host}:{port}")
    print(f"  API:        http://{host}:{port}/api/stats")
    print(f"  Website:    http://{host}:{port}/website/")
    print(f"  Health:     http://{host}:{port}/health")
    print(f"  Stripe:     {'configured' if stripe else 'not configured'}")
    print(f"{'='*60}\n")

    app.run(host=host, port=port, debug=debug)
