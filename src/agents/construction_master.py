#!/usr/bin/env python3
"""
src/agents/construction_master.py — Botwave Construction Master Bot
======================================================================
Multi-tenant Telegram bot where each construction company gets their own
private AI assistant. A single bot process serves ALL tenants, with full
data isolation enforced at the database layer.

Architecture:
  Telegram User → Bot → TenantRouter → TenantSession → TradeProfile
                                            ↓
                              Database (all queries scoped by tenant_id)

Tenant mapping: Each Telegram user is mapped to exactly ONE tenant via
the tenant_users table. The first time an unregistered user messages the
bot, they go through onboarding. Company owners register via /register,
crew members are added via /addcrew by the owner.

Security:
  - Every DB query is scoped by tenant_id — no cross-tenant leakage
  - Owner-only commands require the user to be the tenant creator
  - Secrets loaded from environment — zero hardcoded tokens

Usage:
  export BOTWAVE_MASTER_TOKEN="your-bot-token"
  python -m src.agents.construction_master
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, PhotoSize
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        MessageHandler, filters, ContextTypes, ConversationHandler
    )
except ImportError:
    sys.exit("pip install python-telegram-bot==21.0")

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

from src.core.database import Database, get_db, CustomerRepo, QuoteRepo, AppointmentRepo, LeadRepo, InvoiceRepo
from src.core.schema_v2 import apply_v2_schema
from src.core.construction_repos import (
    TenantConfigRepo, JobRepo, CrewRepo, TimeEntryRepo,
    MaterialRepo, ChangeOrderRepo, TakeoffRepo
)
from src.core.trade_profiles import get_trade_profile, list_supported_trades, TradeProfile

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOTWAVE_MASTER_TOKEN", "")
LLM_URL = os.getenv("LLM_API_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instruct")

logging.basicConfig(format="%(asctime)s %(levelname)s [%(name)s] %(message)s", level=logging.INFO)
logger = logging.getLogger("botwave.master")


# ---------------------------------------------------------------------------
# Tenant Router — maps telegram users to tenants
# ---------------------------------------------------------------------------
TENANT_USERS_DDL = """
CREATE TABLE IF NOT EXISTS tenant_users (
    telegram_id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',
    display_name TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
"""


class TenantRouter:
    """Maps Telegram user IDs to tenant IDs. Single source of truth for isolation."""

    def __init__(self, db: Database):
        self.db = db
        with db.transaction() as conn:
            conn.executescript(TENANT_USERS_DDL)

    def get_tenant_id(self, telegram_id: int) -> Optional[str]:
        row = self.db.query_one(
            "SELECT tenant_id FROM tenant_users WHERE telegram_id = ?",
            (telegram_id,))
        return row["tenant_id"] if row else None

    def get_role(self, telegram_id: int) -> Optional[str]:
        row = self.db.query_one(
            "SELECT role FROM tenant_users WHERE telegram_id = ?",
            (telegram_id,))
        return row["role"] if row else None

    def register_owner(self, telegram_id: int, tenant_id: str, display_name: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO tenant_users (telegram_id, tenant_id, role, display_name) "
            "VALUES (?, ?, 'owner', ?)",
            (telegram_id, tenant_id, display_name))

    def add_crew_user(self, telegram_id: int, tenant_id: str, display_name: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO tenant_users (telegram_id, tenant_id, role, display_name) "
            "VALUES (?, ?, 'crew', ?)",
            (telegram_id, tenant_id, display_name))

    def is_owner(self, telegram_id: int) -> bool:
        return self.get_role(telegram_id) == "owner"


# ---------------------------------------------------------------------------
# Quoting Engine
# ---------------------------------------------------------------------------
class QuotingEngine:
    """Generates quotes using trade profile + tenant config."""

    def __init__(self, tenant_config_repo: TenantConfigRepo):
        self.config_repo = tenant_config_repo

    def generate(self, tenant_id: str, profile: TradeProfile, text: str) -> Optional[Dict]:
        svc = profile.detect_service(text)
        if not svc:
            return None

        rates = self.config_repo.get_labor_rates(tenant_id)
        markups = self.config_repo.get_markups(tenant_id)
        rate = rates.get("journeyman", profile.default_labor_rate)

        labor_low = svc.hours_low * rate
        labor_high = svc.hours_high * rate
        parts_low = svc.parts_low * (1 + markups["materials"] / 100)
        parts_high = svc.parts_high * (1 + markups["materials"] / 100)
        overhead_pct = 1 + markups["overhead"] / 100
        profit_pct = 1 + markups["profit"] / 100

        total_low = (labor_low + parts_low) * overhead_pct * profit_pct
        total_high = (labor_high + parts_high) * overhead_pct * profit_pct

        return {
            "service": svc.name,
            "description": svc.description or text[:200],
            "hours_low": svc.hours_low,
            "hours_high": svc.hours_high,
            "labor_rate": rate,
            "price_low": round(total_low, 2),
            "price_high": round(total_high, 2),
        }


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------
def llm_chat(system_prompt: str, user_message: str, image_b64: str = None) -> str:
    """Send a message to the LLM. Supports text and optional image."""
    messages = [{"role": "system", "content": system_prompt}]

    if image_b64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": user_message},
            ]
        })
    else:
        messages.append({"role": "user", "content": user_message})

    try:
        resp = requests.post(
            f"{LLM_URL}/chat/completions",
            json={"model": LLM_MODEL, "messages": messages, "max_tokens": 1500, "temperature": 0.4},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.error("LLM error: %s", exc)
    return "I'm having trouble connecting to the AI engine right now. Please try again in a moment."


# ---------------------------------------------------------------------------
# Bot Handlers
# ---------------------------------------------------------------------------
db = get_db()
apply_v2_schema(db)

router = TenantRouter(db)
tenant_cfg = TenantConfigRepo(db)
jobs = JobRepo(db)
crew = CrewRepo(db)
time_entries = TimeEntryRepo(db)
materials = MaterialRepo(db)
change_orders = ChangeOrderRepo(db)
takeoffs = TakeoffRepo(db)
quoting = QuotingEngine(tenant_cfg)

# Existing repos
customer_repo = CustomerRepo(db)
quote_repo = QuoteRepo(db)
appointment_repo = AppointmentRepo(db)
lead_repo = LeadRepo(db)
invoice_repo = InvoiceRepo(db)


def _get_profile(tenant_id: str) -> TradeProfile:
    """Get the trade profile for a tenant."""
    cfg = tenant_cfg.get(tenant_id)
    trade_type = cfg["trade_type"] if cfg else "general"
    return get_trade_profile(trade_type)


def _require_tenant(func):
    """Decorator: reject users who aren't registered to a tenant."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        tid = router.get_tenant_id(update.effective_user.id)
        if not tid:
            await update.message.reply_text(
                "You're not registered yet. Use /register to set up your company, "
                "or ask your company owner to add you with /addcrew."
            )
            return
        context.user_data["tenant_id"] = tid
        return await func(update, context)
    return wrapper


def _require_owner(func):
    """Decorator: restrict to tenant owners only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not router.is_owner(update.effective_user.id):
            await update.message.reply_text("This command is restricted to company owners.")
            return
        tid = router.get_tenant_id(update.effective_user.id)
        context.user_data["tenant_id"] = tid
        return await func(update, context)
    return wrapper


# === REGISTRATION ===

async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register a new company. /register CompanyName plumbing"""
    user = update.effective_user
    existing = router.get_tenant_id(user.id)
    if existing:
        await update.message.reply_text("You're already registered to a company. Use /status to check.")
        return

    args = context.args
    if len(args) < 2:
        trades = ", ".join(list_supported_trades())
        await update.message.reply_text(
            f"Usage: `/register CompanyName trade_type`\n\n"
            f"Supported trades: {trades}\n\n"
            f"Example: `/register \"Jimenez Plumbing\" plumbing`",
            parse_mode="Markdown")
        return

    trade_type = args[-1].lower()
    company_name = " ".join(args[:-1]).strip('"').strip("'")

    if trade_type not in list_supported_trades():
        await update.message.reply_text(f"Unknown trade: {trade_type}. Options: {', '.join(list_supported_trades())}")
        return

    tenant_id = f"t_{uuid.uuid4().hex[:10]}"

    # Create tenant
    db.execute(
        "INSERT INTO tenants (id, name, plan, status, trade_type) VALUES (?, ?, 'starter', 'trial', ?)",
        (tenant_id, company_name, trade_type))

    # Create tenant config
    profile = get_trade_profile(trade_type)
    tenant_cfg.upsert(tenant_id,
        trade_type=trade_type,
        labor_rate_journeyman=profile.default_labor_rate,
        minimum_call_out=profile.minimum_call_out,
        bot_greeting=profile.greeting)

    # Register user as owner
    router.register_owner(user.id, tenant_id, user.full_name)

    await update.message.reply_text(
        f"✅ *{company_name}* registered!\n\n"
        f"Trade: {profile.emoji} {profile.display_name}\n"
        f"Plan: Starter (14-day free trial)\n"
        f"Tenant ID: `{tenant_id}`\n\n"
        f"Your Construction Master is ready. Use /help to see what I can do.",
        parse_mode="Markdown")

    logger.info("New tenant registered: %s (%s) by user %d", company_name, trade_type, user.id)


# === CORE COMMANDS ===

@_require_tenant
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    profile = _get_profile(tid)
    keyboard = [
        [InlineKeyboardButton("📋 Get a Quote", callback_data="quote"),
         InlineKeyboardButton("📅 Schedule", callback_data="schedule")],
        [InlineKeyboardButton("👷 My Crew", callback_data="crew"),
         InlineKeyboardButton("⏱ Time Clock", callback_data="timeclock")],
        [InlineKeyboardButton("🏗 Active Jobs", callback_data="jobs"),
         InlineKeyboardButton("📦 Materials", callback_data="materials")],
        [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard"),
         InlineKeyboardButton("❓ Help", callback_data="help")],
    ]
    await update.message.reply_text(
        profile.greeting, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


@_require_tenant
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    profile = _get_profile(tid)
    await update.message.reply_text(
        f"{profile.emoji} *Construction Master Commands*\n\n"
        f"*Bidding & Quotes:*\n"
        f"  /quote `description` — instant price estimate\n"
        f"  Send a 📸 photo — AI takeoff analysis\n\n"
        f"*Jobs & Projects:*\n"
        f"  /newjob `name` `address` — create a job\n"
        f"  /jobs — list active jobs\n"
        f"  /changeorder `job` `description` — log a CO\n\n"
        f"*Crew & Time:*\n"
        f"  /addcrew `name` `role` — add crew member\n"
        f"  /crew — list your crew\n"
        f"  /clockin — start time clock\n"
        f"  /clockout — stop time clock\n"
        f"  /payroll — weekly payroll summary\n\n"
        f"*Materials:*\n"
        f"  /addmaterial `name` `cost` — add to inventory\n"
        f"  /lowstock — check low inventory\n\n"
        f"*Business:*\n"
        f"  /status — company dashboard\n"
        f"  /customers — customer list\n\n"
        f"Or just *type naturally* — I understand your trade.",
        parse_mode="Markdown")


# === QUOTING ===

@_require_tenant
async def cmd_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Describe the job: `/quote kitchen sink clogged`", parse_mode="Markdown")
        return

    profile = _get_profile(tid)
    quote = quoting.generate(tid, profile, text)
    if not quote:
        await update.message.reply_text("I couldn't match that to a service. Can you describe the job in more detail?")
        return

    # Store in database
    quote_repo.create(
        tenant_id=tid, customer_name="Walk-in", service_type=quote["service"],
        description=text, price_low=quote["price_low"], price_high=quote["price_high"],
        estimated_hours=(quote["hours_low"] + quote["hours_high"]) / 2)

    await update.message.reply_text(
        f"📋 *Instant Quote: {quote['service']}*\n\n"
        f"💰 *${quote['price_low']:,.0f} — ${quote['price_high']:,.0f}*\n"
        f"⏱ {quote['hours_low']:.1f}–{quote['hours_high']:.1f} hours labor\n"
        f"👷 Rate: ${quote['labor_rate']:.0f}/hr\n\n"
        f"_Includes materials, overhead, and profit margin._\n"
        f"_Final price after on-site assessment._",
        parse_mode="Markdown")


# === JOBS ===

@_require_owner
async def cmd_newjob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    if len(context.args) < 1:
        await update.message.reply_text("Usage: `/newjob Job Name | 123 Main St`", parse_mode="Markdown")
        return
    full = " ".join(context.args)
    parts = full.split("|")
    name = parts[0].strip()
    address = parts[1].strip() if len(parts) > 1 else ""
    jid = jobs.create(tid, name, address=address)
    await update.message.reply_text(f"🏗 Job created: *{name}*\nID: `{jid}`\nStatus: Bidding", parse_mode="Markdown")


@_require_tenant
async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    active = jobs.list_active(tid)
    if not active:
        await update.message.reply_text("No active jobs. Create one with /newjob")
        return
    lines = ["🏗 *Active Jobs:*\n"]
    for j in active:
        lines.append(f"• *{j['name']}* — {j['status']}\n  📍 {j.get('address') or 'No address'}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# === CREW ===

@_require_owner
async def cmd_addcrew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    if len(context.args) < 1:
        await update.message.reply_text("Usage: `/addcrew John Smith journeyman`", parse_mode="Markdown")
        return
    args = context.args
    role = args[-1] if args[-1] in ("journeyman", "apprentice", "master", "foreman", "laborer") else "journeyman"
    name = " ".join(args[:-1]) if role != args[-1] else " ".join(args)
    cid = crew.add(tid, name, role=role)
    await update.message.reply_text(f"👷 *{name}* added as {role}\nID: `{cid}`", parse_mode="Markdown")


@_require_tenant
async def cmd_crew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    members = crew.list_active(tid)
    if not members:
        await update.message.reply_text("No crew members yet. Owners can add with /addcrew")
        return
    lines = ["👷 *Your Crew:*\n"]
    for m in members:
        rate = f"${m['hourly_rate']:.0f}/hr" if m.get("hourly_rate") else "rate not set"
        lines.append(f"• *{m['name']}* — {m['role']} ({rate})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# === TIME TRACKING ===

@_require_tenant
async def cmd_clockin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    uid = str(update.effective_user.id)
    # Find crew member by telegram mapping (simplified: use first crew member for demo)
    members = crew.list_active(tid)
    if not members:
        await update.message.reply_text("No crew members registered. Add with /addcrew first.")
        return
    member = members[0]  # In production: map telegram_id to crew_member_id
    existing = time_entries.get_open(tid, member["id"])
    if existing:
        await update.message.reply_text(f"⏱ {member['name']} is already clocked in since {existing['clock_in'][:16]}")
        return
    eid = time_entries.clock_in(tid, member["id"])
    await update.message.reply_text(f"✅ *{member['name']}* clocked in\nEntry: `{eid}`", parse_mode="Markdown")


@_require_tenant
async def cmd_clockout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    members = crew.list_active(tid)
    if not members:
        await update.message.reply_text("No crew members registered.")
        return
    member = members[0]
    entry = time_entries.get_open(tid, member["id"])
    if not entry:
        await update.message.reply_text(f"{member['name']} is not clocked in.")
        return
    result = time_entries.clock_out(entry["id"], tid)
    if result:
        await update.message.reply_text(
            f"🛑 *{member['name']}* clocked out\n⏱ Hours: *{result['hours']:.2f}*", parse_mode="Markdown")


@_require_owner
async def cmd_payroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    summary = time_entries.payroll_summary(tid)
    if not summary:
        await update.message.reply_text("No time entries this week.")
        return
    lines = ["💰 *Weekly Payroll Summary:*\n"]
    total_pay = 0
    for row in summary:
        hours = row.get("total_hours") or 0
        pay = row.get("total_pay") or 0
        total_pay += pay
        lines.append(f"• *{row['name']}* ({row['role']}): {hours:.1f}hrs = ${pay:,.2f}")
    lines.append(f"\n*Total: ${total_pay:,.2f}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# === MATERIALS ===

@_require_tenant
async def cmd_lowstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    low = materials.low_stock(tid)
    if not low:
        await update.message.reply_text("📦 All materials above reorder threshold.")
        return
    lines = ["⚠️ *Low Stock Items:*\n"]
    for m in low:
        lines.append(f"• *{m['name']}*: {m['quantity_on_hand']} {m.get('unit', '')} "
                      f"(reorder at {m['reorder_threshold']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# === CHANGE ORDERS ===

@_require_owner
async def cmd_changeorder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/changeorder JOB_ID description of change`", parse_mode="Markdown")
        return
    job_id = context.args[0]
    desc = " ".join(context.args[1:])
    job = jobs.get(job_id, tid)
    if not job:
        await update.message.reply_text(f"Job `{job_id}` not found.")
        return
    coid = change_orders.create(tid, job_id, desc)
    await update.message.reply_text(
        f"📋 *Change Order Created*\nJob: {job['name']}\nCO: `{coid}`\n\n_{desc}_", parse_mode="Markdown")


# === STATUS DASHBOARD ===

@_require_tenant
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tenant_id"]
    tenant = db.query_one("SELECT * FROM tenants WHERE id = ?", (tid,))
    profile = _get_profile(tid)
    j_count = jobs.count(tid)
    c_count = crew.count(tid)
    q_count = quote_repo.count(tid)
    cust_count = customer_repo.count(tid)
    rev = invoice_repo.revenue_total(tid)

    await update.message.reply_text(
        f"{profile.emoji} *{tenant['name']}* — Dashboard\n\n"
        f"📊 *Stats:*\n"
        f"  🏗 Active Jobs: {j_count}\n"
        f"  👷 Crew Members: {c_count}\n"
        f"  📋 Total Quotes: {q_count}\n"
        f"  👥 Customers: {cust_count}\n"
        f"  💰 Revenue: ${rev:,.2f}\n\n"
        f"  📋 Plan: {tenant.get('plan', 'starter').title()}\n"
        f"  🔧 Trade: {profile.display_name}",
        parse_mode="Markdown")


# === PHOTO TAKEOFF (IMAGE HANDLING) ===

@_require_tenant
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process job site photos / blueprint images for takeoff analysis."""
    tid = context.user_data["tenant_id"]
    profile = _get_profile(tid)

    await update.message.reply_text("📸 Analyzing image... this may take a moment.")

    # Get highest resolution photo
    photo: PhotoSize = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    b64 = base64.b64encode(photo_bytes).decode("utf-8")

    # Get caption context
    caption = update.message.caption or "Analyze this job site photo. Estimate materials and labor needed."

    takeoff_prompt = (
        f"{profile.system_prompt}\n\n"
        f"You are analyzing a job site photo or blueprint for a {profile.display_name} contractor. "
        f"Provide:\n"
        f"1. What you see in the image (conditions, scope of work)\n"
        f"2. Estimated materials needed with quantities\n"
        f"3. Estimated labor hours\n"
        f"4. Rough cost range\n"
        f"5. Any concerns or things to watch for\n\n"
        f"Be specific to {profile.display_name.lower()} work. Use industry terminology."
    )

    analysis = llm_chat(takeoff_prompt, caption, image_b64=b64)

    # Store analysis
    takeoffs.store(
        tenant_id=tid,
        analysis_text=analysis,
        image_type="photo",
        original_filename=f"telegram_{photo.file_id[:12]}",
    )

    await update.message.reply_text(
        f"📸 *Takeoff Analysis*\n\n{analysis}", parse_mode="Markdown")


# === FREE TEXT (AI CONVERSATION) ===

@_require_tenant
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route free-text messages through the trade-aware LLM."""
    tid = context.user_data["tenant_id"]
    profile = _get_profile(tid)
    text = update.message.text

    # Try quote detection first
    quote = quoting.generate(tid, profile, text)
    if quote:
        quote_repo.create(
            tenant_id=tid, customer_name=update.effective_user.full_name,
            service_type=quote["service"], description=text,
            price_low=quote["price_low"], price_high=quote["price_high"])

        await update.message.reply_text(
            f"📋 *{quote['service']}*\n\n"
            f"💰 *${quote['price_low']:,.0f} — ${quote['price_high']:,.0f}*\n"
            f"⏱ {quote['hours_low']:.1f}–{quote['hours_high']:.1f} hours\n\n"
            f"_Want more detail? Just ask._",
            parse_mode="Markdown")
        return

    # Fall through to LLM conversation
    tenant = db.query_one("SELECT * FROM tenants WHERE id = ?", (tid,))
    company = tenant["name"] if tenant else "your company"

    system = (
        f"{profile.system_prompt}\n\n"
        f"You are the Construction Master for {company}. "
        f"The user is the business owner or crew member. "
        f"Help them with anything related to running their {profile.display_name.lower()} business. "
        f"Be concise and practical."
    )

    response = llm_chat(system, text)
    await update.message.reply_text(response)


# === CALLBACK HANDLER ===

@_require_tenant
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tid = context.user_data["tenant_id"]

    if data == "help":
        await cmd_help(update, context)
    elif data == "quote":
        await query.edit_message_text("Send me a description of the job and I'll quote it instantly.\n\nExample: _bathroom faucet leaking_", parse_mode="Markdown")
    elif data == "jobs":
        active = jobs.list_active(tid)
        text = "🏗 *Active Jobs:*\n\n" + ("\n".join(f"• {j['name']} — {j['status']}" for j in active) if active else "No active jobs. Use /newjob to create one.")
        await query.edit_message_text(text, parse_mode="Markdown")
    elif data == "crew":
        members = crew.list_active(tid)
        text = "👷 *Your Crew:*\n\n" + ("\n".join(f"• {m['name']} — {m['role']}" for m in members) if members else "No crew yet. Use /addcrew to add.")
        await query.edit_message_text(text, parse_mode="Markdown")
    elif data == "timeclock":
        await query.edit_message_text("⏱ Use /clockin to start and /clockout to stop the time clock.", parse_mode="Markdown")
    elif data == "materials":
        low = materials.low_stock(tid)
        text = "📦 *Low Stock:*\n\n" + ("\n".join(f"• {m['name']}: {m['quantity_on_hand']}" for m in low) if low else "All materials OK.") + "\n\nUse /addmaterial to add inventory."
        await query.edit_message_text(text, parse_mode="Markdown")
    elif data == "schedule":
        upcoming = appointment_repo.list_upcoming(tid)
        text = "📅 *Upcoming:*\n\n" + ("\n".join(f"• {a['customer_name']} — {a['scheduled_date']} {a['scheduled_time']}" for a in upcoming) if upcoming else "No upcoming appointments.")
        await query.edit_message_text(text, parse_mode="Markdown")
    elif data == "dashboard":
        await cmd_status(update, context)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main():
    if not BOT_TOKEN:
        print("=" * 60)
        print("  BOTWAVE CONSTRUCTION MASTER")
        print("=" * 60)
        print("\n  ERROR: Set BOTWAVE_MASTER_TOKEN in your .env\n")
        print("  Get a token from @BotFather on Telegram")
        print("  Then: export BOTWAVE_MASTER_TOKEN='your-token'")
        print("=" * 60)
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("register", cmd_register))

    # Tenant-scoped commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("quote", cmd_quote))
    app.add_handler(CommandHandler("newjob", cmd_newjob))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("addcrew", cmd_addcrew))
    app.add_handler(CommandHandler("crew", cmd_crew))
    app.add_handler(CommandHandler("clockin", cmd_clockin))
    app.add_handler(CommandHandler("clockout", cmd_clockout))
    app.add_handler(CommandHandler("payroll", cmd_payroll))
    app.add_handler(CommandHandler("lowstock", cmd_lowstock))
    app.add_handler(CommandHandler("changeorder", cmd_changeorder))
    app.add_handler(CommandHandler("status", cmd_status))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Photos → takeoff analysis
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Free text → AI conversation
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("=" * 60)
    logger.info("  BOTWAVE CONSTRUCTION MASTER v1.0")
    logger.info("  Trades: %s", ", ".join(list_supported_trades()))
    logger.info("  LLM: %s", LLM_URL)
    logger.info("=" * 60)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
