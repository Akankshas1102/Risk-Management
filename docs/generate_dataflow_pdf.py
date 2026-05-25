"""Generate Data Flow PDF for the Risk Management Dashboard."""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import KeepTogether
from pathlib import Path

OUT = Path(__file__).parent / "Risk_Management_Data_Flow.pdf"

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BG   = colors.HexColor("#1E2A38")
ACCENT    = colors.HexColor("#3B82F6")   # blue
GREEN     = colors.HexColor("#10B981")
ORANGE    = colors.HexColor("#F59E0B")
PURPLE    = colors.HexColor("#8B5CF6")
TEAL      = colors.HexColor("#06B6D4")
WHITE     = colors.white
LIGHT_BG  = colors.HexColor("#F0F4F8")
MID_GRAY  = colors.HexColor("#64748B")
DARK_TEXT = colors.HexColor("#1E293B")

# ── Document ──────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    str(OUT), pagesize=A4,
    leftMargin=18*mm, rightMargin=18*mm,
    topMargin=16*mm, bottomMargin=16*mm,
)

W = A4[0] - 36*mm   # usable width

styles = getSampleStyleSheet()

def sty(name, **kw):
    base = styles[name] if name in styles else styles["Normal"]
    return ParagraphStyle(name + "_custom", parent=base, **kw)

title_sty  = sty("Title", fontSize=22, textColor=WHITE, alignment=TA_CENTER,
                 spaceAfter=4, fontName="Helvetica-Bold")
sub_sty    = sty("Normal", fontSize=10, textColor=colors.HexColor("#93C5FD"),
                 alignment=TA_CENTER, spaceAfter=2)
date_sty   = sty("Normal", fontSize=8, textColor=colors.HexColor("#94A3B8"),
                 alignment=TA_CENTER, spaceAfter=0)
h2_sty     = sty("Heading2", fontSize=13, textColor=DARK_TEXT,
                 fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
body_sty   = sty("Normal", fontSize=9, textColor=DARK_TEXT,
                 leading=14, spaceAfter=3)
mono_sty   = sty("Normal", fontSize=8, fontName="Courier",
                 textColor=colors.HexColor("#1E3A5F"),
                 backColor=colors.HexColor("#EFF6FF"),
                 leading=12, spaceAfter=2, leftIndent=4)
note_sty   = sty("Normal", fontSize=8, textColor=MID_GRAY,
                 leading=12, spaceAfter=2, leftIndent=8)

# ── Helper builders ───────────────────────────────────────────────────────────

def title_block():
    """Dark header banner."""
    data = [[Paragraph("Risk Management Dashboard", title_sty)],
            [Paragraph("Data Flow — Architecture Overview", sub_sty)],
            [Paragraph("SBIT · Vedanta Limited · 2026", date_sty)]]
    t = Table(data, colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BG),
        ("ROWPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",    (0,0), (-1,0), 14),
        ("BOTTOMPADDING", (0,-1), (-1,-1), 14),
        ("ROUNDEDCORNERS", [6]),
    ]))
    return t


def section_header(text, colour):
    data = [[Paragraph(f"<b>{text}</b>",
                       sty("Normal", fontSize=10, textColor=WHITE,
                           fontName="Helvetica-Bold"))]]
    t = Table(data, colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colour),
        ("ROWPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]))
    return t


def flow_box(icon, title, colour, rows):
    """Coloured box with bullet rows."""
    header = [[Paragraph(f"<b>{icon}  {title}</b>",
                         sty("Normal", fontSize=10, textColor=WHITE,
                             fontName="Helvetica-Bold"))]]
    ht = Table(header, colWidths=[W])
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colour),
        ("ROWPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]))

    body_rows = [[Paragraph(f"<bullet>&bull;</bullet> {r}",
                            sty("Normal", fontSize=8.5, textColor=DARK_TEXT,
                                leading=13, leftIndent=8))]
                 for r in rows]
    bt = Table(body_rows, colWidths=[W])
    bt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT_BG),
        ("ROWPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("LINEBELOW", (0,0), (-1,-2), 0.3, colors.HexColor("#CBD5E1")),
        ("BOTTOMPADDING", (0,-1), (-1,-1), 8),
    ]))
    return KeepTogether([ht, bt])


def arrow(label=""):
    lbl = Paragraph(
        f"<font color='#64748B'>▼  {label}</font>" if label else
        "<font color='#64748B'>▼</font>",
        sty("Normal", fontSize=9, textColor=MID_GRAY, alignment=TA_CENTER))
    return lbl


def two_col_table(left_title, left_rows, right_title, right_rows,
                  lc=ACCENT, rc=GREEN):
    col = (W - 4*mm) / 2

    def cell_paragraphs(title, rows, colour):
        """Return a list of Paragraphs for one cell (no nested Tables)."""
        parts = [Paragraph(f"<b>{title}</b>",
                           sty("Normal", fontSize=8.5, textColor=WHITE,
                               fontName="Helvetica-Bold",
                               backColor=colour, leftIndent=4,
                               spaceAfter=3, spaceBefore=3))]
        for r in rows:
            parts.append(Paragraph(
                f"• {r}",
                sty("Normal", fontSize=8, textColor=DARK_TEXT, leading=12,
                    leftIndent=6, spaceAfter=2)))
        return parts

    left_cell  = cell_paragraphs(left_title,  left_rows,  lc)
    right_cell = cell_paragraphs(right_title, right_rows, rc)

    outer = Table([[left_cell, right_cell]], colWidths=[col, col], hAlign="LEFT")
    outer.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,-1), LIGHT_BG),
        ("BACKGROUND",    (1,0), (1,-1), LIGHT_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#CBD5E1")),
    ]))
    return outer


def kv_table(rows, col1=80*mm):
    data = [[Paragraph(f"<b>{k}</b>",
                       sty("Normal", fontSize=8.5, textColor=DARK_TEXT,
                           fontName="Helvetica-Bold")),
             Paragraph(v, sty("Normal", fontSize=8.5, textColor=DARK_TEXT,
                               leading=12))]
            for k, v in rows]
    t = Table(data, colWidths=[col1, W - col1])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT_BG),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, LIGHT_BG]),
        ("ROWPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (0,-1), 10),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#CBD5E1")),
    ]))
    return t


# ── Story ─────────────────────────────────────────────────────────────────────
story = []

# Title
story.append(title_block())
story.append(Spacer(1, 8*mm))

# ── 1. Overview ───────────────────────────────────────────────────────────────
story.append(section_header("1.  High-Level Overview", DARK_BG))
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "The Risk Management Dashboard ingests historical incident data from "
    "<b>Vedanta's SQL Server database</b> (OL_INCIDENTS), runs a four-step "
    "<b>ML pipeline</b> to compute risk scores, forecasts, and SHAP-based "
    "driver attributions, then serves all results through a <b>FastAPI backend</b> "
    "to a <b>React frontend</b>.",
    body_sty))
story.append(Spacer(1, 4*mm))

# ── 2. Data sources ───────────────────────────────────────────────────────────
story.append(flow_box("🗄", "SQL Server — vedanta (Source of Truth)", DARK_BG, [
    "Table: OL_INCIDENTS  ·  ~17,000 rows  ·  37 sites  ·  2020–2026",
    "Columns used: SINAME (site), BUNAME (business unit), YEAR, QUARTER, MONTH, "
    "LEVELNAME (severity), INCIDENTCATNAME (category), OCCUREDDATE, REPORTEDDATE",
    "Populated externally by Vedanta EHS system — this app never writes to OL_INCIDENTS",
    "All 6 ML output tables also live in the same SQL Server database",
]))
story.append(Spacer(1, 4*mm))

# ── 3. ML pipeline ────────────────────────────────────────────────────────────
story.append(section_header("2.  ML Pipeline  (risk_scores → forecasters → backtest → drivers)", ACCENT))
story.append(Spacer(1, 3*mm))

story.append(flow_box("①", "Step 1 — Risk Scores  (≈ 3 s)", GREEN, [
    "Reads all OL_INCIDENTS rows (2020+)",
    "Computes 4 sub-indices per site per quarter:  "
    "Frequency · Severity · Velocity (QoQ growth) · Diversity (Shannon entropy)",
    "Composite score = 0.35·F + 0.30·S + 0.20·V + 0.15·D  → scaled 0–100",
    "Risk level bands:  Low ≤40 · Medium ≤65 · High ≤85 · Critical ≤100",
    "Output → risk_scores table  (777 rows · 37 sites · 2021-Q1 to 2026-Q4)",
]))
story.append(Spacer(1, 2*mm))
story.append(arrow("feeds predictions model"))

story.append(flow_box("②", "Step 2 — Forecasters  (≈ 66 s)", PURPLE, [
    "Builds monthly incident time-series per site from OL_INCIDENTS",
    "Trains Prophet AND XGBoost on each site's series",
    "Champion model = whichever achieves lower holdout RMSE (last 3 months)",
    "When both succeed → ensemble average; sparse sites fall back to BU-level Prophet",
    "Predicts next 3 fiscal quarters  (2026-Q4 · 2026-Q1 · 2026-Q2)",
    "Output → predictions_cache (111 rows) + model_runs training log",
]))
story.append(Spacer(1, 2*mm))
story.append(arrow("evaluates forecast quality"))

story.append(flow_box("③", "Step 3 — Backtest  (≈ 71 s)", TEAL, [
    "6-month walk-forward holdout: train on data before cutoff, predict 6-month window",
    "Metrics: abs_pct_error = |actual − predicted| / actual × 100",
    "MAPE ranges from ~22% (high-volume BALCO) to higher for sparse sites",
    "VLCTPP skipped — insufficient monthly history for holdout window",
    "Output → backtest_results (216 rows · 36 sites × 6 months)",
]))
story.append(Spacer(1, 2*mm))
story.append(arrow("attributes incident categories"))

story.append(flow_box("④", "Step 4 — Drivers & Recommendations  (≈ 58 s)", ORANGE, [
    "SHAP values from XGBoost identify top-10 incident categories driving risk per site",
    "Sparkline: 6-month monthly counts per category (stored as JSON array)",
    "Rules engine fires 8 rules → RecommendationSpec objects "
    "(high_velocity · access_control · material_handling · ir_worker · "
    "asset_property · reporting_lag · process_deviations · generic_fallback)",
    "Output → risk_drivers (278 rows) + recommendations (47 rows)",
]))
story.append(Spacer(1, 4*mm))

# ── 4. Pipeline triggers ──────────────────────────────────────────────────────
story.append(section_header("3.  Pipeline Triggers", MID_GRAY))
story.append(Spacer(1, 3*mm))
story.append(kv_table([
    ("Nightly (APScheduler)",   "Daily at 02:00 UTC · configurable via RETRAIN_CRON env var"),
    ("CSV Upload",              "POST /api/ingest → on_success hook fires run_full_pipeline(trigger='post_ingest')"),
    ("Manual",                  "POST /api/admin/retrain  or  python scripts/run_pipeline.py --trigger manual"),
], col1=55*mm))
story.append(Spacer(1, 4*mm))

# ── 5. API layer ──────────────────────────────────────────────────────────────
story.append(section_header("4.  FastAPI Backend → Frontend", DARK_BG))
story.append(Spacer(1, 3*mm))

story.append(two_col_table(
    "Endpoints (reads SQL Server)",
    [
        "GET /api/sites  ·  /api/kpis",
        "GET /api/incidents/by-type · by-category · by-site · trend · heatmap",
        "GET /api/risk-scores?site=&quarter=&latest_only=",
        "GET /api/predictions?site=  ·  /predictions/backtest",
        "GET /api/drivers?site=  ·  /recommendations?site=",
        "GET /api/admin/freshness  ·  /admin/runs",
        "POST /api/ingest  (CSV upload)",
        "POST /api/admin/retrain  (manual trigger)",
    ],
    "Frontend Tabs (React + React Query)",
    [
        "Overview — KPI cards + breakdown charts",
        "Trends — incident count over time",
        "Risk Drivers — SHAP bars + sparklines",
        "Predictions — forecast + confidence bands",
        "Recommendations — rules-based action items",
        "AI Insights — placeholder stub",
        "Reports — placeholder stub",
    ],
    lc=ACCENT, rc=GREEN,
))
story.append(Spacer(1, 4*mm))

# ── 6. CSV upload detail ──────────────────────────────────────────────────────
story.append(section_header("5.  CSV Upload Flow (only user-triggered write)", TEAL))
story.append(Spacer(1, 3*mm))

steps_data = [
    ["1", "User selects CSV in UI", "Frontend"],
    ["2", "POST /api/ingest → temp file saved", "FastAPI"],
    ["3", "cleaner.py validates rows → quarantine bad dates / bad years", "services/cleaner.py"],
    ["4", "ingestion_runs record created (status: running → success/failed)", "SQL Server"],
    ["5", "on_success hook fires → full pipeline runs in background (~3 min)", "orchestrator.py"],
    ["6", "Dashboard refreshes → serves updated scores & forecasts", "Frontend"],
]
t = Table(steps_data, colWidths=[8*mm, W*0.52, W*0.35])
t.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (0,-1), TEAL),
    ("TEXTCOLOR", (0,0), (0,-1), WHITE),
    ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, LIGHT_BG]),
    ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
    ("ALIGN", (0,0), (0,-1), "CENTER"),
    ("FONTSIZE", (0,0), (-1,-1), 8.5),
    ("ROWPADDING", (0,0), (-1,-1), 5),
    ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#CBD5E1")),
    ("LEFTPADDING", (1,0), (1,-1), 8),
]))
story.append(t)
story.append(Spacer(1, 4*mm))

# ── 7. Key constraint ─────────────────────────────────────────────────────────
story.append(section_header("6.  Key Constraints & Design Decisions", ORANGE))
story.append(Spacer(1, 3*mm))
story.append(kv_table([
    ("OL_INCIDENTS",         "Read-only. Never written by this app. External Vedanta EHS system is the only writer."),
    ("Sole database",        "SQL Server vedanta. Postgres stack was retired 2026-05-25."),
    ("api/ + schemas/",      "Vinay's territory — API files and Pydantic schemas are not modified by the ML team."),
    ("Fiscal quarters",      "Q4 = Jan–Mar · Q1 = Apr–Jun · Q2 = Jul–Sep · Q3 = Oct–Dec"),
    ("Site normalisation",   "OL_INCIDENTS has mixed-case site names. All normalised to UPPER STRIP before scoring."),
    ("Sparse-site fallback", "Sites with <50 incidents or <12 months of data fall back to BU-level Prophet scaled by historical share."),
], col1=52*mm))
story.append(Spacer(1, 6*mm))

# ── Footer ────────────────────────────────────────────────────────────────────
story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor("#CBD5E1")))
story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "Risk Management Dashboard · SBIT · Vedanta Limited · Generated 2026-05-25",
    sty("Normal", fontSize=7.5, textColor=MID_GRAY, alignment=TA_CENTER)))

# ── Build ─────────────────────────────────────────────────────────────────────
doc.build(story)
print(f"PDF written -> {OUT}")
