#!/usr/bin/env python3
"""
src/takeoff_engine.py — Botwave Structured Takeoff & Bid Engine
===================================================================
Turns a job site photo + LLM analysis into a structured bid document.

The pipeline:
  1. Photo comes in via Telegram (or dashboard upload)
  2. LLM (local or cloud) analyzes the image with a structured prompt
  3. Response is parsed into line items (materials, labor, costs)
  4. Tenant markups/rates are applied to produce a real bid
  5. PDF bid document is generated with the tenant's branding
  6. Stored in the database with full audit trail

This is the module that makes the photo takeoff feature a real product —
not just a text dump, but a professional document a contractor can
hand to a homeowner or send to a supplier.

Usage:
    from src.takeoff_engine import TakeoffEngine
    engine = TakeoffEngine(db)
    result = engine.analyze_photo(tenant_id, image_b64, caption)
    pdf_path = engine.generate_bid_pdf(result)
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("botwave.takeoff")

# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MaterialLine:
    """A single material line item in a takeoff."""
    name: str
    quantity: float
    unit: str
    unit_cost: float
    total: float
    category: str = ""
    notes: str = ""

@dataclass
class LaborLine:
    """A labor line item in a takeoff."""
    task: str
    hours_low: float
    hours_high: float
    rate: float
    total_low: float
    total_high: float
    skill_level: str = "journeyman"

@dataclass
class TakeoffResult:
    """Complete structured takeoff from a photo analysis."""
    id: str
    tenant_id: str
    job_description: str
    scope_of_work: str
    conditions_observed: str
    concerns: List[str]

    materials: List[MaterialLine]
    labor: List[LaborLine]

    materials_subtotal: float
    labor_subtotal_low: float
    labor_subtotal_high: float

    overhead_pct: float
    profit_pct: float
    materials_markup_pct: float

    total_low: float
    total_high: float

    # Metadata
    trade_type: str = ""
    confidence: str = "medium"
    permit_required: bool = False
    permit_estimate: float = 0.0
    timeline_days_low: int = 1
    timeline_days_high: int = 3
    warranty_notes: str = ""
    exclusions: List[str] = field(default_factory=list)

    raw_analysis: str = ""
    image_filename: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_text(self) -> str:
        """Generate a Telegram-friendly summary."""
        lines = [
            f"📋 *Takeoff Estimate*\n",
            f"*Scope:* {self.scope_of_work[:200]}",
            "",
            f"📦 *Materials:* ${self.materials_subtotal:,.0f}",
        ]
        for m in self.materials[:8]:
            lines.append(f"  • {m.name}: {m.quantity:.0f} {m.unit} (${m.total:,.0f})")
        if len(self.materials) > 8:
            lines.append(f"  _...and {len(self.materials) - 8} more items_")

        lines.append(f"\n👷 *Labor:* ${self.labor_subtotal_low:,.0f}–${self.labor_subtotal_high:,.0f}")
        for l in self.labor[:5]:
            lines.append(f"  • {l.task}: {l.hours_low:.1f}–{l.hours_high:.1f}hrs @ ${l.rate:.0f}/hr")

        lines.append(f"\n{'─' * 30}")
        lines.append(f"💰 *Total Estimate: ${self.total_low:,.0f} – ${self.total_high:,.0f}*")
        lines.append(f"📅 Timeline: {self.timeline_days_low}–{self.timeline_days_high} days")
        if self.permit_required:
            lines.append(f"📋 Permit required (~${self.permit_estimate:,.0f})")
        if self.concerns:
            lines.append(f"\n⚠️ *Watch out for:*")
            for c in self.concerns[:3]:
                lines.append(f"  • {c}")

        lines.append(f"\n_Confidence: {self.confidence} | Includes {self.overhead_pct:.0f}% overhead + {self.profit_pct:.0f}% profit_")
        lines.append(f"_Final price after on-site verification._")

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED LLM PROMPT — Forces JSON output from the vision model
# ─────────────────────────────────────────────────────────────────────────────

TAKEOFF_SYSTEM_PROMPT = """You are a senior {trade_type} estimator analyzing a job site photo.
You produce accurate, itemized takeoffs that contractors use for real bids.

RESPOND ONLY WITH A JSON OBJECT. No markdown, no explanation, no preamble.
The JSON must follow this exact structure:

{{
  "scope_of_work": "Brief description of the work needed",
  "conditions_observed": "What you see in the photo — existing conditions, damage, access issues",
  "concerns": ["concern 1", "concern 2"],
  "permit_required": true/false,
  "permit_estimate": 0,
  "timeline_days_low": 1,
  "timeline_days_high": 3,
  "confidence": "low" | "medium" | "high",
  "warranty_notes": "Standard 1-year warranty on labor",
  "exclusions": ["things NOT included in this estimate"],
  "materials": [
    {{
      "name": "Material name",
      "quantity": 1.0,
      "unit": "each/ft/gal/box/roll",
      "unit_cost": 0.00,
      "category": "pipe/fitting/fixture/wire/misc",
      "notes": ""
    }}
  ],
  "labor": [
    {{
      "task": "Task description",
      "hours_low": 1.0,
      "hours_high": 2.0,
      "skill_level": "journeyman/apprentice/master"
    }}
  ]
}}

RULES:
- Use realistic current material prices for the {service_area} area
- Include ALL materials needed (pipe, fittings, connectors, tape, hangers, etc.)
- Break labor into distinct tasks (demo, rough-in, finish, cleanup, etc.)
- Be specific: "3/4 inch copper pipe" not just "pipe"
- If you can't determine something from the photo, say so in concerns
- Always include cleanup and haul-off in labor
- Round unit costs to nearest dollar

Return ONLY the JSON. No other text."""


# ─────────────────────────────────────────────────────────────────────────────
# TAKEOFF ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TakeoffEngine:
    """Orchestrates the photo → structured takeoff → bid document pipeline."""

    def __init__(self, db, llm_url: str = None, llm_model: str = None):
        self.db = db
        self.llm_url = llm_url or os.getenv("LLM_API_URL", "http://localhost:1234/v1")
        self.llm_model = llm_model or os.getenv("LLM_MODEL", "llama-3.1-8b-instruct")

        # Lazy imports for repos
        from src.core.construction_repos import TenantConfigRepo, TakeoffRepo
        self.config_repo = TenantConfigRepo(db)
        self.takeoff_repo = TakeoffRepo(db)

    def _call_llm(self, system: str, user_msg: str, image_b64: str = None) -> str:
        """Call the local LLM (or cloud fallback) with optional image."""
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests library required")

        messages = [{"role": "system", "content": system}]

        if image_b64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": user_msg},
                ]
            })
        else:
            messages.append({"role": "user", "content": user_msg})

        try:
            resp = requests.post(
                f"{self.llm_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": messages,
                    "max_tokens": 3000,
                    "temperature": 0.2,  # Low temp for structured output
                },
                timeout=90,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("LLM call failed: %s", e)

        return ""

    def _parse_llm_json(self, raw: str) -> dict:
        """Extract JSON from LLM response (handles markdown fences, preamble, etc.)."""
        # Try direct parse
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Strip markdown fences
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Find first { to last }
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse LLM JSON response")
        return {}

    def analyze_photo(
        self,
        tenant_id: str,
        image_b64: str,
        caption: str = "",
        job_id: str = None,
        image_filename: str = "",
    ) -> TakeoffResult:
        """
        Full pipeline: photo → LLM → structured takeoff with tenant pricing applied.

        Returns a TakeoffResult with itemized materials, labor, and totals.
        """
        # Get tenant config for rates and markups
        cfg = self.config_repo.get(tenant_id) or {}
        trade_type = cfg.get("trade_type", "general")
        service_area = cfg.get("service_area", "San Diego, CA")

        rates = self.config_repo.get_labor_rates(tenant_id)
        markups = self.config_repo.get_markups(tenant_id)

        # Build the prompt
        system = TAKEOFF_SYSTEM_PROMPT.format(
            trade_type=trade_type,
            service_area=service_area,
        )

        user_msg = caption or "Analyze this job site photo. Provide a complete itemized takeoff."

        # Call LLM
        logger.info("Analyzing photo for tenant %s (trade: %s)", tenant_id, trade_type)
        raw_response = self._call_llm(system, user_msg, image_b64)

        if not raw_response:
            return self._empty_result(tenant_id, "LLM returned empty response", markups)

        # Parse structured response
        data = self._parse_llm_json(raw_response)
        if not data:
            return self._fallback_result(tenant_id, raw_response, markups, caption)

        # Build material lines with markup
        materials = []
        mat_subtotal = 0
        for m in data.get("materials", []):
            qty = float(m.get("quantity", 0))
            unit_cost = float(m.get("unit_cost", 0))
            total = qty * unit_cost
            mat_subtotal += total
            materials.append(MaterialLine(
                name=m.get("name", "Unknown"),
                quantity=qty,
                unit=m.get("unit", "each"),
                unit_cost=unit_cost,
                total=total,
                category=m.get("category", ""),
                notes=m.get("notes", ""),
            ))

        # Apply materials markup
        mat_marked_up = mat_subtotal * (1 + markups["materials"] / 100)

        # Build labor lines with tenant rates
        labor = []
        labor_low = 0
        labor_high = 0
        for l in data.get("labor", []):
            skill = l.get("skill_level", "journeyman")
            rate = rates.get(skill, rates.get("journeyman", 95.0))
            h_low = float(l.get("hours_low", 0))
            h_high = float(l.get("hours_high", 0))
            labor.append(LaborLine(
                task=l.get("task", ""),
                hours_low=h_low,
                hours_high=h_high,
                rate=rate,
                total_low=h_low * rate,
                total_high=h_high * rate,
                skill_level=skill,
            ))
            labor_low += h_low * rate
            labor_high += h_high * rate

        # Calculate totals with overhead and profit
        overhead_pct = markups["overhead"]
        profit_pct = markups["profit"]

        subtotal_low = mat_marked_up + labor_low
        subtotal_high = mat_marked_up + labor_high

        total_low = subtotal_low * (1 + overhead_pct / 100) * (1 + profit_pct / 100)
        total_high = subtotal_high * (1 + overhead_pct / 100) * (1 + profit_pct / 100)

        # Add permit if applicable
        permit_est = float(data.get("permit_estimate", 0))
        if data.get("permit_required") and permit_est > 0:
            total_low += permit_est
            total_high += permit_est

        result = TakeoffResult(
            id=f"tkoff_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            job_description=caption or "Photo takeoff analysis",
            scope_of_work=data.get("scope_of_work", ""),
            conditions_observed=data.get("conditions_observed", ""),
            concerns=data.get("concerns", []),
            materials=materials,
            labor=labor,
            materials_subtotal=round(mat_marked_up, 2),
            labor_subtotal_low=round(labor_low, 2),
            labor_subtotal_high=round(labor_high, 2),
            overhead_pct=overhead_pct,
            profit_pct=profit_pct,
            materials_markup_pct=markups["materials"],
            total_low=round(total_low, 2),
            total_high=round(total_high, 2),
            trade_type=trade_type,
            confidence=data.get("confidence", "medium"),
            permit_required=data.get("permit_required", False),
            permit_estimate=permit_est,
            timeline_days_low=int(data.get("timeline_days_low", 1)),
            timeline_days_high=int(data.get("timeline_days_high", 3)),
            warranty_notes=data.get("warranty_notes", "Standard 1-year warranty on labor"),
            exclusions=data.get("exclusions", []),
            raw_analysis=raw_response,
            image_filename=image_filename,
            created_at=datetime.utcnow().isoformat(),
        )

        # Store in database
        self._store_result(result, job_id)

        logger.info("Takeoff complete: %s (materials: $%.0f, labor: $%.0f-$%.0f, total: $%.0f-$%.0f)",
                     result.id, mat_marked_up, labor_low, labor_high, total_low, total_high)

        return result

    def _store_result(self, result: TakeoffResult, job_id: str = None):
        """Store the structured takeoff in the database."""
        self.takeoff_repo.store(
            tenant_id=result.tenant_id,
            analysis_text=result.raw_analysis,
            job_id=job_id,
            image_type="photo",
            original_filename=result.image_filename,
            extracted_measurements=json.dumps([asdict(m) for m in result.materials]),
            material_suggestions=json.dumps([asdict(l) for l in result.labor]),
            cost_estimate_low=result.total_low,
            cost_estimate_high=result.total_high,
            confidence_score={"low": 0.3, "medium": 0.6, "high": 0.85}.get(result.confidence, 0.5),
        )

    def _empty_result(self, tenant_id, error_msg, markups):
        return TakeoffResult(
            id=f"tkoff_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            job_description=error_msg,
            scope_of_work="Unable to analyze — LLM unavailable",
            conditions_observed="",
            concerns=["AI analysis unavailable — manual takeoff required"],
            materials=[], labor=[],
            materials_subtotal=0, labor_subtotal_low=0, labor_subtotal_high=0,
            overhead_pct=markups["overhead"], profit_pct=markups["profit"],
            materials_markup_pct=markups["materials"],
            total_low=0, total_high=0,
            confidence="low",
            created_at=datetime.utcnow().isoformat(),
        )

    def _fallback_result(self, tenant_id, raw, markups, caption):
        """When JSON parsing fails, return raw text as a note."""
        return TakeoffResult(
            id=f"tkoff_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            job_description=caption or "Photo analysis",
            scope_of_work=raw[:500],
            conditions_observed="(Unstructured analysis — see raw text)",
            concerns=["AI returned unstructured text — manual review needed"],
            materials=[], labor=[],
            materials_subtotal=0, labor_subtotal_low=0, labor_subtotal_high=0,
            overhead_pct=markups["overhead"], profit_pct=markups["profit"],
            materials_markup_pct=markups["materials"],
            total_low=0, total_high=0,
            confidence="low",
            raw_analysis=raw,
            created_at=datetime.utcnow().isoformat(),
        )

    # ─────────────────────────────────────────────────────────────────────
    # PDF BID DOCUMENT GENERATOR
    # ─────────────────────────────────────────────────────────────────────

    def generate_bid_pdf(
        self,
        result: TakeoffResult,
        output_dir: str = None,
        company_name: str = None,
        company_phone: str = None,
        company_license: str = None,
    ) -> str:
        """
        Generate a professional PDF bid document from a TakeoffResult.
        Returns the file path of the generated PDF.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                HRFlowable, KeepTogether
            )
        except ImportError:
            logger.error("reportlab required for PDF generation: pip install reportlab")
            return ""

        # Get tenant info
        cfg = self.config_repo.get(result.tenant_id) or {}
        tenant = self.db.query_one("SELECT * FROM tenants WHERE id = ?", (result.tenant_id,))

        co_name = company_name or (tenant["name"] if tenant else "Construction Company")
        co_phone = company_phone or cfg.get("company_phone", "")
        co_license = company_license or cfg.get("company_license", "")

        # Output path
        if not output_dir:
            output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "bids")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filename = f"BID-{result.id}-{datetime.now().strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(output_dir, filename)

        # Colors
        NAVY = colors.HexColor("#0B1426")
        TEAL = colors.HexColor("#0891B2")
        DARK = colors.HexColor("#1E293B")
        MUTED = colors.HexColor("#64748B")
        LIGHT = colors.HexColor("#F1F5F9")
        GREEN = colors.HexColor("#10B981")
        WHITE = colors.white

        # Styles
        styles = getSampleStyleSheet()
        s_title = ParagraphStyle("BidTitle", fontName="Helvetica-Bold", fontSize=22, textColor=NAVY, spaceAfter=4)
        s_subtitle = ParagraphStyle("BidSub", fontName="Helvetica", fontSize=10, textColor=MUTED, spaceAfter=16)
        s_section = ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=12, textColor=TEAL, spaceBefore=16, spaceAfter=8)
        s_body = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.5, textColor=DARK, leading=13, spaceAfter=4)
        s_small = ParagraphStyle("Small", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=10)
        s_total = ParagraphStyle("Total", fontName="Helvetica-Bold", fontSize=14, textColor=NAVY)
        s_right = ParagraphStyle("Right", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, alignment=TA_RIGHT)

        elements = []

        # ── Header ──
        header_data = [
            [Paragraph(f"<b>{co_name}</b>", ParagraphStyle("Co", fontName="Helvetica-Bold", fontSize=16, textColor=NAVY)),
             Paragraph(f"BID ESTIMATE<br/><font size=8 color='#64748B'>{result.id}</font>",
                       ParagraphStyle("BidLabel", fontName="Helvetica-Bold", fontSize=12, textColor=TEAL, alignment=TA_RIGHT))],
        ]
        if co_phone or co_license:
            detail = f"{co_phone}" + (f"  |  Lic# {co_license}" if co_license else "")
            header_data.append([
                Paragraph(detail, s_small),
                Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", ParagraphStyle("Date", fontName="Helvetica", fontSize=9, textColor=MUTED, alignment=TA_RIGHT)),
            ])

        header_table = Table(header_data, colWidths=[4 * inch, 3.5 * inch])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(header_table)
        elements.append(HRFlowable(width="100%", thickness=2, color=TEAL, spaceAfter=16))

        # ── Scope ──
        elements.append(Paragraph("Scope of Work", s_section))
        elements.append(Paragraph(result.scope_of_work, s_body))
        if result.conditions_observed:
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"<b>Site Conditions:</b> {result.conditions_observed}", s_body))

        # ── Materials Table ──
        if result.materials:
            elements.append(Paragraph("Materials", s_section))
            mat_header = ["Item", "Qty", "Unit", "Unit Cost", "Total"]
            mat_data = [mat_header]
            for m in result.materials:
                mat_data.append([
                    m.name + (f"\n({m.notes})" if m.notes else ""),
                    f"{m.quantity:.1f}",
                    m.unit,
                    f"${m.unit_cost:,.2f}",
                    f"${m.total:,.2f}",
                ])
            mat_data.append(["", "", "", Paragraph("<b>Subtotal</b>", s_right),
                             f"${result.materials_subtotal:,.2f}"])

            mat_table = Table(mat_data, colWidths=[2.8 * inch, 0.6 * inch, 0.6 * inch, 1.2 * inch, 1.2 * inch])
            mat_style = [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#E2E8F0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1.5, NAVY),
            ]
            mat_table.setStyle(TableStyle(mat_style))
            elements.append(mat_table)
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(f"<i>Materials include {result.materials_markup_pct:.0f}% markup</i>", s_small))

        # ── Labor Table ──
        if result.labor:
            elements.append(Paragraph("Labor", s_section))
            lab_data = [["Task", "Skill", "Hours", "Rate", "Estimate"]]
            for l in result.labor:
                lab_data.append([
                    l.task,
                    l.skill_level.capitalize(),
                    f"{l.hours_low:.1f}–{l.hours_high:.1f}",
                    f"${l.rate:,.0f}/hr",
                    f"${l.total_low:,.0f}–${l.total_high:,.0f}",
                ])
            lab_data.append(["", "", "", Paragraph("<b>Subtotal</b>", s_right),
                             f"${result.labor_subtotal_low:,.0f}–${result.labor_subtotal_high:,.0f}"])

            lab_table = Table(lab_data, colWidths=[2.4 * inch, 1.0 * inch, 0.8 * inch, 0.9 * inch, 1.3 * inch])
            lab_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#E2E8F0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1.5, NAVY),
            ]))
            elements.append(lab_table)

        # ── Totals Box ──
        elements.append(Spacer(1, 16))
        totals_data = [
            ["Materials (with markup)", f"${result.materials_subtotal:,.2f}"],
            ["Labor", f"${result.labor_subtotal_low:,.0f} – ${result.labor_subtotal_high:,.0f}"],
            [f"Overhead ({result.overhead_pct:.0f}%)", "included"],
            [f"Profit ({result.profit_pct:.0f}%)", "included"],
        ]
        if result.permit_required:
            totals_data.append(["Permit (estimated)", f"${result.permit_estimate:,.0f}"])
        totals_data.append(["TOTAL ESTIMATE", f"${result.total_low:,.0f} – ${result.total_high:,.0f}"])

        totals_table = Table(totals_data, colWidths=[4.5 * inch, 2 * inch])
        totals_table.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("TEXTCOLOR", (0, 0), (-1, -2), DARK),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEABOVE", (0, -1), (-1, -1), 2, TEAL),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 13),
            ("TEXTCOLOR", (0, -1), (-1, -1), NAVY),
            ("TOPPADDING", (0, -1), (-1, -1), 8),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0FDFA")),
        ]))
        elements.append(totals_table)

        # ── Timeline ──
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Project Details", s_section))
        details = f"<b>Estimated Timeline:</b> {result.timeline_days_low}–{result.timeline_days_high} business days"
        if result.warranty_notes:
            details += f"<br/><b>Warranty:</b> {result.warranty_notes}"
        elements.append(Paragraph(details, s_body))

        # ── Concerns ──
        if result.concerns:
            elements.append(Paragraph("Notes & Concerns", s_section))
            for c in result.concerns:
                elements.append(Paragraph(f"• {c}", s_body))

        # ── Exclusions ──
        if result.exclusions:
            elements.append(Paragraph("Exclusions", s_section))
            for e in result.exclusions:
                elements.append(Paragraph(f"• {e}", s_body))

        # ── Footer ──
        elements.append(Spacer(1, 24))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=MUTED, spaceAfter=8))
        elements.append(Paragraph(
            f"This estimate is valid for 30 days from the date of issue. "
            f"Final pricing subject to on-site verification. "
            f"Generated by Botwave AI ({result.confidence} confidence).",
            s_small
        ))

        # ── Signature Block ──
        elements.append(Spacer(1, 24))
        sig_data = [
            [Paragraph("<b>Accepted By:</b>", s_body), "", Paragraph("<b>Date:</b>", s_body), ""],
            ["_" * 35, "", "_" * 20, ""],
            [Paragraph("Customer Signature", s_small), "", Paragraph("Date", s_small), ""],
        ]
        sig_table = Table(sig_data, colWidths=[3 * inch, 0.5 * inch, 2 * inch, 1 * inch])
        sig_table.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(sig_table)

        # Build PDF
        doc = SimpleDocTemplate(
            filepath, pagesize=letter,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        )
        doc.build(elements)

        logger.info("Bid PDF generated: %s", filepath)
        return filepath


# ─────────────────────────────────────────────────────────────────────────────
# ENHANCED TELEGRAM HANDLER — Drop-in replacement for handle_photo
# ─────────────────────────────────────────────────────────────────────────────

def create_enhanced_photo_handler(db):
    """
    Returns an async handler that replaces the existing handle_photo
    in construction_master.py. Produces structured takeoffs + PDF bids.

    Usage in construction_master.py:
        from src.takeoff_engine import create_enhanced_photo_handler
        enhanced_photo = create_enhanced_photo_handler(db)
        # Then in your handler registration:
        app.add_handler(MessageHandler(filters.PHOTO, enhanced_photo))
    """
    engine = TakeoffEngine(db)

    async def handle_photo_enhanced(update, context):
        """Process job site photos into structured takeoffs with PDF bid generation."""
        import base64
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        tid = context.user_data.get("tenant_id")
        if not tid:
            await update.message.reply_text("You're not registered. Use /register first.")
            return

        await update.message.reply_text("📸 Analyzing photo... building your takeoff estimate.")

        # Get photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        b64 = base64.b64encode(photo_bytes).decode("utf-8")
        caption = update.message.caption or "Analyze this job site photo for a complete takeoff."

        # Run the engine
        result = engine.analyze_photo(
            tenant_id=tid,
            image_b64=b64,
            caption=caption,
            image_filename=f"telegram_{photo.file_id[:12]}",
        )

        # Send structured summary
        await update.message.reply_text(
            result.summary_text(),
            parse_mode="Markdown",
        )

        # Generate PDF bid
        try:
            pdf_path = engine.generate_bid_pdf(result)
            if pdf_path and os.path.exists(pdf_path):
                keyboard = [[
                    InlineKeyboardButton("📋 Create Job from This", callback_data=f"job_from_takeoff:{result.id}"),
                    InlineKeyboardButton("📤 Email to Customer", callback_data=f"email_bid:{result.id}"),
                ]]
                with open(pdf_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=os.path.basename(pdf_path),
                        caption="📄 Professional bid document attached.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
        except Exception as e:
            logger.error("PDF generation failed: %s", e)
            await update.message.reply_text(
                "_(Bid PDF generation unavailable — install reportlab: pip install reportlab)_",
                parse_mode="Markdown",
            )

    return handle_photo_enhanced
