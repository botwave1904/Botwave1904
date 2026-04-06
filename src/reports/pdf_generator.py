#!/usr/bin/env python3
"""
src/reports/pdf_generator.py — Botwave PDF Report Generator
=============================================================
Generates professional PDF reports for service businesses:
  - Service Reports (per-job summaries with line items)
  - Monthly Analytics (charts, KPIs, trends)
  - Audit Reports (system health, compliance)

Uses only Python stdlib + minimal dependencies for portability.
Outputs clean, branded PDFs ready for client delivery.

Usage:
    from src.reports.pdf_generator import ReportGenerator
    gen = ReportGenerator()
    gen.service_report(customer, quote, output_path="report.pdf")
    gen.analytics_report(stats, output_path="analytics.pdf")
"""

import io
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# reportlab is standard for Python PDF generation
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
except ImportError:
    print("PDF reports require reportlab. Install: pip install reportlab")
    sys.exit(1)


# Brand colors
BRAND_NAVY = colors.HexColor("#0B1426")
BRAND_TEAL = colors.HexColor("#0891B2")
BRAND_GREEN = colors.HexColor("#10B981")
BRAND_DARK = colors.HexColor("#1E293B")
BRAND_MUTED = colors.HexColor("#64748B")
BRAND_LIGHT = colors.HexColor("#F1F5F9")
WHITE = colors.white


class ReportGenerator:
    """Generates branded PDF reports for Botwave service businesses."""

    def __init__(self, company_name: str = "Botwave", company_tagline: str = "AI Automation for Service Businesses"):
        self.company_name = company_name
        self.company_tagline = company_tagline
        self.styles = getSampleStyleSheet()
        self._register_styles()

    def _register_styles(self):
        self.styles.add(ParagraphStyle(
            name="BrandTitle", fontName="Helvetica-Bold", fontSize=24,
            textColor=BRAND_NAVY, spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name="BrandSubtitle", fontName="Helvetica", fontSize=12,
            textColor=BRAND_MUTED, spaceAfter=20
        ))
        self.styles.add(ParagraphStyle(
            name="SectionHeader", fontName="Helvetica-Bold", fontSize=14,
            textColor=BRAND_TEAL, spaceBefore=16, spaceAfter=8
        ))
        self.styles.add(ParagraphStyle(
            name="BwBody", fontName="Helvetica", fontSize=10,
            textColor=BRAND_DARK, leading=14, spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name="SmallMuted", fontName="Helvetica", fontSize=8,
            textColor=BRAND_MUTED
        ))
        self.styles.add(ParagraphStyle(
            name="KPIValue", fontName="Helvetica-Bold", fontSize=28,
            textColor=BRAND_TEAL, alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name="KPILabel", fontName="Helvetica", fontSize=9,
            textColor=BRAND_MUTED, alignment=TA_CENTER, spaceAfter=8
        ))

    def _header_footer(self, canvas, doc):
        canvas.saveState()
        # Header line
        canvas.setStrokeColor(BRAND_TEAL)
        canvas.setLineWidth(2)
        canvas.line(inch * 0.75, letter[1] - inch * 0.6, letter[0] - inch * 0.75, letter[1] - inch * 0.6)
        # Header text
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(BRAND_NAVY)
        canvas.drawString(inch * 0.75, letter[1] - inch * 0.5, self.company_name)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(BRAND_MUTED)
        canvas.drawRightString(letter[0] - inch * 0.75, letter[1] - inch * 0.5, "CONFIDENTIAL")
        # Footer
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(BRAND_MUTED)
        canvas.drawString(inch * 0.75, inch * 0.5, f"{self.company_name} — {self.company_tagline}")
        canvas.drawRightString(letter[0] - inch * 0.75, inch * 0.5, f"Page {doc.page}")
        canvas.restoreState()

    def _build_doc(self, output_path: str, elements: list):
        doc = SimpleDocTemplate(
            output_path, pagesize=letter,
            topMargin=inch * 0.9, bottomMargin=inch * 0.8,
            leftMargin=inch * 0.75, rightMargin=inch * 0.75,
        )
        doc.build(elements, onFirstPage=self._header_footer, onLaterPages=self._header_footer)

    def _make_table(self, data: List[List], col_widths: List[float] = None,
                    header: bool = True) -> Table:
        style_cmds = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), BRAND_DARK),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BRAND_LIGHT]),
        ]
        if header:
            style_cmds.extend([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
            ])

        tbl = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
        tbl.setStyle(TableStyle(style_cmds))
        return tbl

    # -----------------------------------------------------------------------
    # Service Report (per-job)
    # -----------------------------------------------------------------------
    def service_report(self, customer: Dict, quote: Dict,
                       line_items: List[Dict] = None,
                       notes: str = "",
                       output_path: str = "service_report.pdf") -> str:
        elements = []

        # Title
        elements.append(Paragraph("Service Report", self.styles["BrandTitle"]))
        elements.append(Paragraph(
            f"Generated {datetime.now().strftime('%B %d, %Y')}",
            self.styles["BrandSubtitle"]
        ))
        elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_TEAL, spaceAfter=16))

        # Customer info
        elements.append(Paragraph("Customer Information", self.styles["SectionHeader"]))
        info_data = [
            ["Customer", customer.get("name", "—")],
            ["Phone", customer.get("phone", "—")],
            ["Email", customer.get("email", "—")],
            ["Address", customer.get("address", "—")],
        ]
        elements.append(self._make_table(info_data, col_widths=[2 * inch, 4.5 * inch], header=False))
        elements.append(Spacer(1, 16))

        # Service details
        elements.append(Paragraph("Service Details", self.styles["SectionHeader"]))
        service_data = [
            ["Service Type", quote.get("service_type", "—")],
            ["Description", quote.get("description", "—")],
            ["Price Range", f"${quote.get('price_low', 0):,.2f} — ${quote.get('price_high', 0):,.2f}"],
            ["Estimated Hours", str(quote.get("estimated_hours", "—"))],
            ["Status", quote.get("status", "pending").upper()],
        ]
        elements.append(self._make_table(service_data, col_widths=[2 * inch, 4.5 * inch], header=False))
        elements.append(Spacer(1, 16))

        # Line items
        if line_items:
            elements.append(Paragraph("Line Items", self.styles["SectionHeader"]))
            items_data = [["Item", "Description", "Qty", "Unit Price", "Total"]]
            grand_total = 0
            for item in line_items:
                total = item.get("quantity", 1) * item.get("unit_price", 0)
                grand_total += total
                items_data.append([
                    item.get("name", ""),
                    item.get("description", ""),
                    str(item.get("quantity", 1)),
                    f"${item.get('unit_price', 0):,.2f}",
                    f"${total:,.2f}",
                ])
            items_data.append(["", "", "", "TOTAL", f"${grand_total:,.2f}"])
            elements.append(self._make_table(items_data, col_widths=[1.2*inch, 2.5*inch, 0.6*inch, 1.1*inch, 1.1*inch]))
            elements.append(Spacer(1, 16))

        # Notes
        if notes:
            elements.append(Paragraph("Notes", self.styles["SectionHeader"]))
            elements.append(Paragraph(notes, self.styles["BwBody"]))

        self._build_doc(output_path, elements)
        return output_path

    # -----------------------------------------------------------------------
    # Analytics Report (monthly)
    # -----------------------------------------------------------------------
    def analytics_report(self, stats: Dict, period: str = None,
                         output_path: str = "analytics_report.pdf") -> str:
        period = period or datetime.now().strftime("%B %Y")
        elements = []

        # Title
        elements.append(Paragraph("Monthly Analytics Report", self.styles["BrandTitle"]))
        elements.append(Paragraph(f"Period: {period}", self.styles["BrandSubtitle"]))
        elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_TEAL, spaceAfter=16))

        # KPI cards as a table
        elements.append(Paragraph("Key Performance Indicators", self.styles["SectionHeader"]))
        kpi_data = [[
            Paragraph(f"{stats.get('customers', 0)}", self.styles["KPIValue"]),
            Paragraph(f"{stats.get('quotes', 0)}", self.styles["KPIValue"]),
            Paragraph(f"{stats.get('appointments', 0)}", self.styles["KPIValue"]),
            Paragraph(f"${stats.get('revenue', 0):,.0f}", self.styles["KPIValue"]),
        ], [
            Paragraph("Customers", self.styles["KPILabel"]),
            Paragraph("Quotes", self.styles["KPILabel"]),
            Paragraph("Appointments", self.styles["KPILabel"]),
            Paragraph("Revenue", self.styles["KPILabel"]),
        ]]
        kpi_table = Table(kpi_data, colWidths=[1.625 * inch] * 4)
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, 0), 16),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 20))

        # Pipeline summary
        elements.append(Paragraph("Pipeline Summary", self.styles["SectionHeader"]))
        pipeline = [
            ["Metric", "Count", "Status"],
            ["New Leads", str(stats.get("new_leads", 0)), "Requires Follow-Up"],
            ["Pending Quotes", str(stats.get("pending_quotes", 0)), "Awaiting Response"],
            ["Upcoming Appointments", str(stats.get("upcoming_appointments", 0)), "Scheduled"],
            ["Total Customers", str(stats.get("customers", 0)), "Active"],
        ]
        elements.append(self._make_table(pipeline, col_widths=[2.5 * inch, 1.5 * inch, 2.5 * inch]))
        elements.append(Spacer(1, 20))

        # Recommendations
        elements.append(Paragraph("Recommendations", self.styles["SectionHeader"]))
        recs = []
        if stats.get("new_leads", 0) > 5:
            recs.append("High lead volume — consider adding a second agent for faster follow-up.")
        if stats.get("pending_quotes", 0) > 10:
            recs.append("Many pending quotes — automated follow-up reminders could improve conversion.")
        if stats.get("revenue", 0) < 1000:
            recs.append("Revenue is below target — review pricing tiers and upsell opportunities.")
        if not recs:
            recs.append("All metrics look healthy. Keep up the great work!")
        for rec in recs:
            elements.append(Paragraph(f"• {rec}", self.styles["BwBody"]))

        self._build_doc(output_path, elements)
        return output_path

    # -----------------------------------------------------------------------
    # Audit Report
    # -----------------------------------------------------------------------
    def audit_report(self, system_status: Dict, checks: List[Dict] = None,
                     output_path: str = "audit_report.pdf") -> str:
        elements = []

        elements.append(Paragraph("System Audit Report", self.styles["BrandTitle"]))
        elements.append(Paragraph(
            f"Generated {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}",
            self.styles["BrandSubtitle"]
        ))
        elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_TEAL, spaceAfter=16))

        # System status
        elements.append(Paragraph("System Status", self.styles["SectionHeader"]))
        status_data = [["Component", "Status"]]
        for component, status in system_status.items():
            status_data.append([component, status])
        elements.append(self._make_table(status_data, col_widths=[3.25 * inch, 3.25 * inch]))
        elements.append(Spacer(1, 16))

        # Checks
        if checks:
            elements.append(Paragraph("Audit Checks", self.styles["SectionHeader"]))
            check_data = [["Check", "Result", "Details"]]
            for check in checks:
                check_data.append([
                    check.get("name", ""),
                    "PASS" if check.get("passed") else "FAIL",
                    check.get("detail", ""),
                ])
            elements.append(self._make_table(check_data, col_widths=[2 * inch, 1 * inch, 3.5 * inch]))

        self._build_doc(output_path, elements)
        return output_path


# ---------------------------------------------------------------------------
# CLI usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    gen = ReportGenerator(company_name="Jimenez Plumbing", company_tagline="Professional Plumbing Services")

    # Demo: generate a sample service report
    sample_customer = {"name": "John Smith", "phone": "(555) 123-4567", "email": "john@example.com", "address": "123 Main St, San Diego, CA"}
    sample_quote = {"service_type": "Drain Cleaning", "description": "Kitchen sink clogged, slow drain for 2 weeks", "price_low": 185, "price_high": 350, "estimated_hours": 2, "status": "accepted"}
    sample_items = [
        {"name": "Service Call", "description": "On-site diagnosis", "quantity": 1, "unit_price": 95},
        {"name": "Drain Snake", "description": "Mechanical drain clearing", "quantity": 1, "unit_price": 150},
        {"name": "Parts", "description": "P-trap replacement", "quantity": 1, "unit_price": 35},
    ]

    out = gen.service_report(sample_customer, sample_quote, line_items=sample_items,
                              notes="Customer satisfied. Recommended annual drain maintenance.", output_path="demo_service_report.pdf")
    print(f"Service report: {out}")

    # Demo: analytics report
    sample_stats = {"customers": 47, "quotes": 123, "appointments": 89, "revenue": 28750, "new_leads": 12, "pending_quotes": 8, "upcoming_appointments": 5}
    out2 = gen.analytics_report(sample_stats, output_path="demo_analytics_report.pdf")
    print(f"Analytics report: {out2}")

    # Demo: audit report
    sample_system = {"Dashboard": "RUNNING", "Telegram Bot": "RUNNING", "Database": "HEALTHY", "Stripe": "CONFIGURED", "LM Studio": "RUNNING"}
    sample_checks = [
        {"name": "Database connectivity", "passed": True, "detail": "SQLite responding, WAL mode active"},
        {"name": "API endpoints", "passed": True, "detail": "All 12 endpoints returning 200"},
        {"name": "Stripe webhook", "passed": True, "detail": "Webhook secret configured"},
        {"name": "Disk space", "passed": True, "detail": "42 GB free (78%)"},
        {"name": "SSL certificate", "passed": False, "detail": "Certificate expires in 12 days — renew soon"},
    ]
    out3 = gen.audit_report(sample_system, sample_checks, output_path="demo_audit_report.pdf")
    print(f"Audit report: {out3}")
