"""
Trucking Trade Profile for Botwave
===================================
Add this to src/core/trade_profiles.py — paste above the TRADE_REGISTRY dict
and add "trucking": TRUCKING to the registry.

This profile transforms Botwave from a construction-only platform into one
that also serves owner-operators and small trucking companies (1-15 trucks).

The "service catalog" concept maps differently for trucking:
- Instead of "Drain Cleaning" with hours + parts, trucking has
  "Load Evaluation" with cost-per-mile + estimated revenue
- hours_low/high become "estimated_hours_driving"
- parts_low/high become "estimated_variable_cost" (fuel, tolls, etc.)

The quoting engine interprets these naturally:
  total_cost = (hours * labor_rate) + parts = (drive_hours * rate/hr) + fuel_and_tolls
"""

# ──────────────────────────────────────────────────────────────────────
# Paste this block into trade_profiles.py, above TRADE_REGISTRY
# ──────────────────────────────────────────────────────────────────────

TRUCKING = TradeProfile(
    trade_type="trucking",
    display_name="Trucking",
    emoji="🚛",
    default_labor_rate=25.0,  # $/hour for driver pay context (owner-op thinks in $/mile but system needs $/hr)
    minimum_call_out=0.0,     # No call-out fee in trucking — this is per-load
    specialties=[
        "dry van", "flatbed", "reefer", "tanker", "hotshot",
        "LTL", "FTL", "owner-operator", "small fleet", "expedited"
    ],
    capabilities=[
        "quotes",           # → "rate check" — is this load worth running?
        "scheduling",       # → "load scheduling" — when to pick up, deliver
        "crew",             # → "driver management" — who's available, HOS
        "time_tracking",    # → "trip logging" — departure/arrival times
        "materials",        # → "fuel & expense tracking"
        "change_orders",    # → "detention/accessorial charges"
        "takeoffs",         # → "BOL-to-invoice" from photo
        "customers",        # → "broker/shipper management"
    ],
    greeting=(
        "🚛 *Welcome to Botwave — Trucking Edition!*\n\n"
        "I'm your AI dispatcher and back-office assistant. I can help with:\n\n"
        "💰 Rate checks — is this load worth running?\n"
        "📄 Instant invoices from BOL photos\n"
        "⛽ Fuel & expense tracking\n"
        "🔧 Maintenance scheduling & reminders\n"
        "📊 Cost-per-mile breakdowns\n"
        "🧾 IFTA fuel log from receipt photos\n"
        "👥 Driver availability & HOS tracking\n\n"
        "What do you need help with?"
    ),
    system_prompt=(
        "You are a Botwave AI assistant specializing in TRUCKING. "
        "You work for a small trucking company or owner-operator. "
        "You speak trucker — talk about lanes, deadhead, per-mile rates, "
        "lumper fees, detention, DAT averages, spot vs contract, "
        "IFTA, HOS, pre-trip inspections, and broker reliability. "
        "You're direct, practical, and always thinking about the bottom line. "
        "When evaluating a load, always calculate: revenue per mile, "
        "cost per mile (fuel + insurance + maintenance + truck payment), "
        "profit per mile, total profit, and deadhead cost. "
        "Average operating cost for an owner-operator is $1.70-$2.20/mile "
        "depending on equipment and insurance costs. "
        "Always remind them to factor in deadhead miles and unpaid wait time. "
        "Keep responses concise and dollar-focused."
    ),
    services=[
        # ── Load Evaluation (the core "quoting" function for trucking) ──
        # hours_low/high = estimated drive hours
        # parts_low/high = estimated variable costs (fuel, tolls)
        ServiceDef(
            "Load Evaluation",
            hours_low=4.0, hours_high=12.0,
            parts_low=200, parts_high=800,
            keywords=["load", "rate", "worth it", "should i take", "lane",
                       "per mile", "rate check", "freight", "haul", "run"],
            description="Evaluate whether a load is profitable based on rate, distance, and operating costs"
        ),
        ServiceDef(
            "Deadhead Analysis",
            hours_low=1.0, hours_high=6.0,
            parts_low=100, parts_high=400,
            keywords=["deadhead", "empty miles", "reposition", "bobtail",
                       "no load", "get to pickup", "drive empty"],
            description="Calculate the cost of driving empty to a pickup location"
        ),
        ServiceDef(
            "Invoice Generation",
            hours_low=0.1, hours_high=0.5,
            parts_low=0, parts_high=0,
            keywords=["invoice", "bill", "bol", "bill of lading", "get paid",
                       "send invoice", "billing", "payment"],
            description="Generate a professional invoice from load details or BOL photo"
        ),
        ServiceDef(
            "Fuel Expense Logging",
            hours_low=0.0, hours_high=0.0,
            parts_low=0, parts_high=0,
            keywords=["fuel", "diesel", "gas", "fill up", "receipt",
                       "fuel stop", "ifta", "gallons"],
            description="Log fuel purchases for expense tracking and IFTA reporting"
        ),
        ServiceDef(
            "IFTA Calculation",
            hours_low=0.5, hours_high=2.0,
            parts_low=0, parts_high=0,
            keywords=["ifta", "fuel tax", "quarterly", "state miles",
                       "tax report", "mileage by state"],
            description="Calculate IFTA fuel tax liability by state/province"
        ),
        ServiceDef(
            "Maintenance Scheduling",
            hours_low=0.5, hours_high=4.0,
            parts_low=50, parts_high=2000,
            keywords=["maintenance", "oil change", "tire", "brake",
                       "service", "repair", "inspection", "pre-trip",
                       "dot inspection", "annual"],
            description="Track and schedule preventive maintenance by mileage or date"
        ),
        ServiceDef(
            "Detention/Accessorial",
            hours_low=1.0, hours_high=8.0,
            parts_low=0, parts_high=0,
            keywords=["detention", "wait", "waiting", "lumper", "accessorial",
                       "layover", "tarp", "twic", "scale", "overweight"],
            description="Track detention time and accessorial charges for billing"
        ),
        ServiceDef(
            "Operating Cost Analysis",
            hours_low=0.5, hours_high=1.0,
            parts_low=0, parts_high=0,
            keywords=["cost per mile", "operating cost", "expenses",
                       "profit margin", "break even", "what am i making",
                       "am i profitable", "overhead"],
            description="Break down true cost-per-mile including fixed and variable costs"
        ),
        ServiceDef(
            "Broker/Shipper Lookup",
            hours_low=0.0, hours_high=0.0,
            parts_low=0, parts_high=0,
            keywords=["broker", "shipper", "carrier packet", "setup",
                       "mc number", "authority", "credit check", "days to pay"],
            description="Check broker reliability, payment terms, and credit worthiness"
        ),
        ServiceDef(
            "Trip Planning",
            hours_low=2.0, hours_high=12.0,
            parts_low=100, parts_high=600,
            keywords=["trip", "route", "plan", "drive time", "hours",
                       "hos", "rest stop", "parking", "fuel stop plan"],
            description="Plan trips considering HOS limits, fuel stops, and parking availability"
        ),
        ServiceDef(
            "Insurance/Compliance",
            hours_low=0.5, hours_high=2.0,
            parts_low=0, parts_high=0,
            keywords=["insurance", "compliance", "dot", "fmcsa", "authority",
                       "medical card", "drug test", "cdl", "registration"],
            description="Track compliance deadlines, insurance renewals, and CDL requirements"
        ),
        # Catch-all
        ServiceDef(
            "General Trucking",
            hours_low=1.0, hours_high=4.0,
            parts_low=50, parts_high=300,
            keywords=[],
            description="General trucking business assistance"
        ),
    ],
)


# ──────────────────────────────────────────────────────────────────────
# Then add to TRADE_REGISTRY:
#
# TRADE_REGISTRY: Dict[str, TradeProfile] = {
#     "plumbing": PLUMBING,
#     "electrical": ELECTRICAL,
#     "roofing": ROOFING,
#     "general": GENERAL_CONTRACTOR,
#     "hvac": HVAC,
#     "trucking": TRUCKING,    # ← add this line
# }
# ──────────────────────────────────────────────────────────────────────
