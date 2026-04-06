#!/usr/bin/env python3
"""
src/core/trade_profiles.py — Trade-Aware Configuration System
================================================================
Each tenant has a trade_type. This module maps trade types to:
  - System prompt personality (how the bot talks)
  - Service catalog (what it quotes)
  - Keyword detection (intent parsing)
  - Pricing rules (labor rates, parts estimates)
  - Enabled capabilities (which commands the bot exposes)

Adding a new trade: add a TradeProfile to TRADE_REGISTRY below.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ServiceDef:
    """A single service a trade offers."""
    name: str
    hours_low: float
    hours_high: float
    parts_low: float
    parts_high: float
    keywords: List[str]
    description: str = ""


@dataclass
class TradeProfile:
    """Complete personality and capabilities for one trade type."""
    trade_type: str
    display_name: str
    emoji: str
    system_prompt: str
    greeting: str
    services: List[ServiceDef]
    capabilities: List[str] = field(default_factory=lambda: [
        "quotes", "scheduling", "crew", "time_tracking",
        "materials", "change_orders", "takeoffs", "customers"
    ])
    default_labor_rate: float = 95.0
    minimum_call_out: float = 185.0
    specialties: List[str] = field(default_factory=list)

    def detect_service(self, text: str) -> Optional[ServiceDef]:
        """Match user text to the most specific service."""
        text_lower = text.lower()
        best_match = None
        best_score = 0
        for svc in self.services:
            score = sum(1 for kw in svc.keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_match = svc
        return best_match


# ==========================================================================
# TRADE REGISTRY — add new trades here
# ==========================================================================

PLUMBING = TradeProfile(
    trade_type="plumbing",
    display_name="Plumbing",
    emoji="🔧",
    default_labor_rate=95.0,
    minimum_call_out=185.0,
    specialties=["residential", "commercial", "grease traps", "slab leaks", "repiping"],
    greeting=(
        "👷 *Welcome to your Construction Master — Plumbing Edition!*\n\n"
        "I'm your AI assistant for running your plumbing business. I can help with:\n\n"
        "🔧 Instant quotes and bid generation\n"
        "📸 Photo takeoffs and material estimates\n"
        "📅 Scheduling and crew management\n"
        "⏱ Time tracking and payroll\n"
        "📦 Material ordering and inventory\n"
        "📋 Change order management\n\n"
        "What do you need help with?"
    ),
    system_prompt=(
        "You are a Construction Master AI assistant specializing in PLUMBING. "
        "You work for a plumbing contractor and speak their language — "
        "talk about rough-ins, DWV, supply lines, slab leaks, grease traps, "
        "water heaters, PRVs, and code compliance. "
        "You're direct, practical, and business-focused. "
        "When quoting, always factor in labor, materials, permit costs, and overhead. "
        "For San Diego area: journeyman rate ~$95/hr, master ~$135/hr. "
        "Always confirm scope before locking a price. "
        "Keep responses concise and actionable."
    ),
    services=[
        ServiceDef("Drain Cleaning", 1.0, 2.0, 50, 150, ["clog", "drain", "slow", "backup", "blocked", "snake"]),
        ServiceDef("Leak Repair", 1.5, 4.0, 100, 400, ["leak", "drip", "water damage", "pipe", "burst", "broken pipe"]),
        ServiceDef("Water Heater", 3.0, 6.0, 600, 2500, ["heater", "hot water", "no hot", "tank", "tankless"]),
        ServiceDef("Toilet Repair", 0.5, 1.5, 30, 200, ["toilet", "flush", "running", "overflow", "wax ring"]),
        ServiceDef("Faucet/Fixture", 1.0, 2.5, 80, 500, ["faucet", "tap", "sink", "fixture", "install"]),
        ServiceDef("Sewer Line", 3.0, 8.0, 300, 3000, ["sewer", "main line", "sewage", "smell", "camera", "root"]),
        ServiceDef("Gas Line", 2.0, 5.0, 200, 1500, ["gas", "gas line", "gas leak", "gas pipe"]),
        ServiceDef("Repipe", 8.0, 24.0, 2000, 8000, ["repipe", "repiping", "whole house", "copper", "pex"]),
        ServiceDef("Grease Trap", 2.0, 4.0, 300, 1200, ["grease trap", "grease interceptor", "restaurant"]),
        ServiceDef("Slab Leak", 4.0, 12.0, 500, 5000, ["slab leak", "under slab", "foundation"]),
        ServiceDef("General Plumbing", 1.0, 3.0, 50, 300, []),
    ],
)

ELECTRICAL = TradeProfile(
    trade_type="electrical",
    display_name="Electrical",
    emoji="⚡",
    default_labor_rate=105.0,
    minimum_call_out=200.0,
    specialties=["residential", "commercial", "panel upgrades", "EV chargers", "solar"],
    greeting=(
        "⚡ *Welcome to your Construction Master — Electrical Edition!*\n\n"
        "I'm your AI assistant for your electrical contracting business.\n\n"
        "⚡ Quotes and bid generation\n"
        "📸 Photo takeoffs from job sites\n"
        "📅 Scheduling and crew assignments\n"
        "⏱ Time tracking and payroll\n"
        "📦 Parts inventory management\n\n"
        "What do you need?"
    ),
    system_prompt=(
        "You are a Construction Master AI assistant specializing in ELECTRICAL work. "
        "You speak electrician — panels, circuits, breakers, conduit, wire gauges, "
        "load calculations, NEC code, GFCI/AFCI, EV chargers, solar tie-ins. "
        "You're direct and safety-conscious. Always mention permits and inspections "
        "when relevant. Journeyman rate ~$105/hr, master ~$145/hr in San Diego area."
    ),
    services=[
        ServiceDef("Outlet/Switch", 0.5, 1.5, 20, 100, ["outlet", "switch", "plug", "receptacle", "gfci"]),
        ServiceDef("Panel Upgrade", 4.0, 10.0, 800, 3000, ["panel", "breaker box", "200 amp", "upgrade", "main"]),
        ServiceDef("Lighting Install", 1.0, 4.0, 50, 800, ["light", "lighting", "fixture", "chandelier", "recessed", "can light"]),
        ServiceDef("Wiring/Rewire", 4.0, 20.0, 500, 5000, ["wire", "wiring", "rewire", "knob and tube", "romex"]),
        ServiceDef("EV Charger", 3.0, 6.0, 400, 1500, ["ev charger", "tesla", "electric car", "charging station"]),
        ServiceDef("Troubleshooting", 1.0, 3.0, 30, 200, ["no power", "tripping", "short", "flickering", "buzzing"]),
        ServiceDef("General Electrical", 1.0, 3.0, 50, 300, []),
    ],
)

ROOFING = TradeProfile(
    trade_type="roofing",
    display_name="Roofing",
    emoji="🏠",
    default_labor_rate=85.0,
    minimum_call_out=250.0,
    specialties=["shingle", "tile", "flat roof", "TPO", "metal", "repair", "re-roof"],
    greeting=(
        "🏠 *Welcome to your Construction Master — Roofing Edition!*\n\n"
        "I'm your AI assistant for your roofing business.\n\n"
        "🏠 Roof quotes and square footage estimates\n"
        "📸 Photo takeoffs from drone/site pics\n"
        "📅 Crew scheduling by weather\n"
        "⏱ Time tracking for jobs\n"
        "📦 Material estimates (bundles, squares)\n\n"
        "What do you need?"
    ),
    system_prompt=(
        "You are a Construction Master AI assistant specializing in ROOFING. "
        "You speak roofer — squares, bundles, underlayment, flashing, drip edge, "
        "ridge vents, valleys, crickets, TPO, EPDM, standing seam. "
        "Always price per square (100 sq ft). Factor in tear-off, dump fees, "
        "and weather delays. Typical crew is 4-6 guys."
    ),
    services=[
        ServiceDef("Roof Repair", 2.0, 6.0, 100, 800, ["leak", "repair", "patch", "missing shingle", "damage"]),
        ServiceDef("Re-Roof (Shingle)", 16.0, 40.0, 3000, 15000, ["re-roof", "new roof", "shingle", "asphalt", "replace"]),
        ServiceDef("Re-Roof (Tile)", 20.0, 60.0, 5000, 25000, ["tile roof", "clay", "concrete tile"]),
        ServiceDef("Flat Roof", 8.0, 24.0, 2000, 10000, ["flat roof", "tpo", "epdm", "built-up", "torch down"]),
        ServiceDef("Gutter Install", 4.0, 8.0, 400, 1500, ["gutter", "downspout", "rain", "drainage"]),
        ServiceDef("General Roofing", 2.0, 8.0, 200, 1000, []),
    ],
)

GENERAL_CONTRACTOR = TradeProfile(
    trade_type="general",
    display_name="General Contracting",
    emoji="🏗️",
    default_labor_rate=90.0,
    minimum_call_out=250.0,
    specialties=["remodel", "addition", "new construction", "tenant improvement"],
    greeting=(
        "🏗️ *Welcome to your Construction Master — GC Edition!*\n\n"
        "I'm your AI assistant for managing your general contracting business.\n\n"
        "🏗️ Project bids and estimates\n"
        "📸 Blueprint and site photo analysis\n"
        "📅 Sub scheduling and coordination\n"
        "⏱ Crew time tracking\n"
        "📋 Change order management\n"
        "📦 Material procurement\n\n"
        "What do you need?"
    ),
    system_prompt=(
        "You are a Construction Master AI assistant for a GENERAL CONTRACTOR. "
        "You manage the big picture — subs, schedules, permits, inspections, "
        "change orders, owner communication. You understand all trades at a "
        "coordination level. You think in terms of critical path, float, "
        "cost codes, and margin protection. Always keep the owner informed "
        "about budget impact of any scope change."
    ),
    services=[
        ServiceDef("Kitchen Remodel", 80.0, 200.0, 15000, 60000, ["kitchen", "remodel", "cabinets", "countertop"]),
        ServiceDef("Bathroom Remodel", 40.0, 120.0, 8000, 35000, ["bathroom", "shower", "tub", "tile"]),
        ServiceDef("Room Addition", 160.0, 500.0, 30000, 150000, ["addition", "add room", "expand", "build out"]),
        ServiceDef("Tenant Improvement", 40.0, 200.0, 10000, 80000, ["tenant improvement", "ti", "build out", "commercial"]),
        ServiceDef("Handyman/Repair", 2.0, 8.0, 50, 500, ["handyman", "repair", "fix", "small job"]),
        ServiceDef("General Construction", 8.0, 40.0, 1000, 10000, []),
    ],
)

HVAC = TradeProfile(
    trade_type="hvac",
    display_name="HVAC",
    emoji="❄️",
    default_labor_rate=100.0,
    minimum_call_out=195.0,
    specialties=["residential AC", "commercial HVAC", "ductwork", "mini-split"],
    greeting=(
        "❄️ *Welcome to your Construction Master — HVAC Edition!*\n\n"
        "I'm your AI assistant for your HVAC business.\n\n"
        "❄️ Quotes for install, repair, and maintenance\n"
        "📸 Site photo analysis for load calcs\n"
        "📅 Service scheduling\n"
        "⏱ Tech time tracking\n"
        "📦 Parts and equipment ordering\n\n"
        "What do you need?"
    ),
    system_prompt=(
        "You are a Construction Master AI assistant specializing in HVAC. "
        "You speak HVAC — tonnage, SEER ratings, BTUs, ductwork sizing, "
        "refrigerant charges, blower motors, heat pumps, mini-splits. "
        "Always factor in equipment, labor, permits, and duct modifications. "
        "Remind about seasonal maintenance contracts as upsell opportunities."
    ),
    services=[
        ServiceDef("AC Repair", 1.5, 4.0, 100, 800, ["ac", "air conditioning", "not cooling", "warm air", "compressor"]),
        ServiceDef("Furnace Repair", 1.5, 4.0, 100, 600, ["furnace", "heater", "no heat", "heating", "ignitor"]),
        ServiceDef("AC Install", 6.0, 12.0, 3000, 8000, ["new ac", "install ac", "replace ac", "new unit"]),
        ServiceDef("Mini-Split", 4.0, 8.0, 1500, 5000, ["mini split", "ductless", "wall unit"]),
        ServiceDef("Duct Work", 4.0, 16.0, 500, 3000, ["duct", "ductwork", "air flow", "vent"]),
        ServiceDef("Maintenance", 1.0, 2.0, 30, 100, ["tune up", "maintenance", "filter", "check up", "seasonal"]),
        ServiceDef("General HVAC", 1.5, 4.0, 100, 500, []),
    ],
)


# ==========================================================================
# REGISTRY LOOKUP
# ==========================================================================
TRADE_REGISTRY: Dict[str, TradeProfile] = {
    "plumbing": PLUMBING,
    "electrical": ELECTRICAL,
    "roofing": ROOFING,
    "general": GENERAL_CONTRACTOR,
    "hvac": HVAC,
}


def get_trade_profile(trade_type: str) -> TradeProfile:
    """Get trade profile by type. Falls back to general contractor."""
    return TRADE_REGISTRY.get(trade_type, GENERAL_CONTRACTOR)


def list_supported_trades() -> List[str]:
    return list(TRADE_REGISTRY.keys())
