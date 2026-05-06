import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import anthropic
import base64

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Pulse Check | Zehn Finance",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Branding colors ──────────────────────────────────────────────────
NAVY = "#002060"
GOLD = "#B8961E"
GOLD_L = "#F0C75A"
RED = "#C0392B"
GREEN = "#1D9E75"
AMBER = "#D4780A"
LT_RED = "#FDF2F2"
LT_GREEN = "#EAF7EE"
LT_AMBER = "#FFF8ED"
LT_BLUE = "#E6F0FF"

# ── Custom CSS ───────────────────────────────────────────────────────
st.markdown(f"""
<style>
    .stApp {{
        background-color: #F7F8FA;
    }}
    .header-bar {{
        background: {NAVY};
        padding: 20px 32px;
        border-radius: 0;
        margin: -1rem -1rem 1.5rem -1rem;
    }}
    .header-bar h1 {{
        color: white;
        font-size: 24px;
        margin: 0;
        font-weight: 600;
    }}
    .header-bar .subtitle {{
        color: {GOLD_L};
        font-size: 12px;
        letter-spacing: 2px;
        font-weight: 600;
    }}
    .gradient-bar {{
        height: 4px;
        background: linear-gradient(90deg, #E24B4A, {GOLD_L}, #4A90D9, {GREEN});
        margin: -1rem -1rem 0 -1rem;
    }}
    .metric-card {{
        background: white;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        border: 1px solid #E2E6EC;
    }}
    .signal-pass {{ border-left: 4px solid {GREEN}; background: {LT_GREEN}; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 8px; }}
    .signal-caution {{ border-left: 4px solid {AMBER}; background: {LT_AMBER}; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 8px; }}
    .signal-fail {{ border-left: 4px solid {RED}; background: {LT_RED}; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 8px; }}
    .narrative-box {{ background: {LT_BLUE}; border-radius: 6px; padding: 10px 14px; margin-top: 6px; font-size: 14px; color: {NAVY}; }}
    div[data-testid="stMetric"] {{
        background: white;
        border: 1px solid #E2E6EC;
        border-radius: 10px;
        padding: 12px 16px;
    }}
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────
st.markdown('<div class="gradient-bar"></div>', unsafe_allow_html=True)
st.markdown(f"""
<div class="header-bar">
    <div class="subtitle">ZEHN FINANCE</div>
    <h1>Financial Pulse Check</h1>
    <div style="color: rgba(255,255,255,0.4); font-size: 13px; margin-top: 4px;">
        Upload 3 years of financials. See what the numbers are signalling.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Line items definition ────────────────────────────────────────────
LINE_ITEMS = {
    "Income Statement": [
        ("revenue", "Revenue"),
        ("cogs", "Cost of Goods Sold (COGS)"),
        ("gross_profit", "Gross Profit"),
        ("sga", "SG&A / Operating Expenses"),
        ("ebitda", "EBITDA"),
        ("da", "Depreciation & Amortization"),
        ("interest", "Interest Expense"),
        ("net_profit", "Net Profit"),
    ],
    "Balance Sheet": [
        ("ar", "Accounts Receivable"),
        ("inventory", "Inventory"),
        ("ap", "Accounts Payable"),
        ("total_debt", "Total Debt"),
        ("cash", "Cash & Equivalents"),
        ("total_assets", "Total Assets"),
    ],
    "Cash Flow": [
        ("ocf", "Operating Cash Flow"),
        ("capex", "Capital Expenditure"),
    ],
    "Additional Context": [
        ("num_customers", "Number of Customers"),
        ("top1_revenue", "Revenue from Top Customer"),
        ("top5_revenue", "Revenue from Top 5 Customers"),
        ("related_party", "Related Party Transactions"),
    ],
}

ALL_KEYS = []
for items in LINE_ITEMS.values():
    ALL_KEYS.extend([k for k, _ in items])

SAMPLE_DATA = {
    "revenue": [80000, 95000, 110000],
    "cogs": [32000, 38000, 46000],
    "gross_profit": [48000, 57000, 64000],
    "sga": [28000, 33000, 39000],
    "ebitda": [20000, 24000, 25000],
    "da": [5000, 6000, 7000],
    "interest": [2000, 2500, 3500],
    "net_profit": [10000, 12000, 11000],
    "ar": [12000, 16000, 24000],
    "inventory": [8000, 10000, 15000],
    "ap": [6000, 7000, 7500],
    "total_debt": [30000, 35000, 50000],
    "cash": [15000, 12000, 8000],
    "total_assets": [90000, 105000, 130000],
    "ocf": [18000, 20000, 15000],
    "capex": [6000, 5000, 4000],
    "num_customers": [120, 135, 142],
    "top1_revenue": [12000, 15000, 22000],
    "top5_revenue": [35000, 42000, 55000],
    "related_party": [2000, 3000, 8000],
}

# ── Helper functions ─────────────────────────────────────────────────
def safe(val):
    try:
        return float(val) if val is not None and val != "" else 0
    except (ValueError, TypeError):
        return 0

def pct_change(a, b):
    if b and b != 0:
        return (a - b) / abs(b)
    return None

def fmt_pct(n):
    if n is None or not isinstance(n, (int, float)):
        return "—"
    return f"{n*100:.1f}%"

def fmt_num(n):
    if n is None:
        return "—"
    return f"{n:,.0f}"

# ── Red flag engine ──────────────────────────────────────────────────
def run_signals(d):
    def g(key, yr):
        return safe(d.get(key, [0,0,0])[yr])
    
    flags = []
    
    # 1. EBITDA vs OCF divergence
    ebitda_growth = pct_change(g("ebitda",2), g("ebitda",0))
    ocf_growth = pct_change(g("ocf",2), g("ocf",0))
    status = "fail" if (ebitda_growth and ebitda_growth > 0 and ocf_growth is not None and ocf_growth < 0) else \
             "caution" if (ebitda_growth and ebitda_growth > 0 and ocf_growth is not None and ocf_growth < ebitda_growth * 0.5) else "pass"
    flags.append({"id": 1, "name": "EBITDA vs Cash Flow Divergence", "category": "Earnings Quality",
        "desc": "EBITDA growing while operating cash flow is declining.", "status": status,
        "detail": f"EBITDA growth: {fmt_pct(ebitda_growth)} | OCF growth: {fmt_pct(ocf_growth)}"})
    
    # 2. Revenue vs OCF
    rev_growth = pct_change(g("revenue",2), g("revenue",0))
    status = "fail" if (rev_growth and rev_growth > 0 and ocf_growth is not None and rev_growth > ocf_growth * 1.5) else \
             "caution" if (rev_growth and rev_growth > 0 and ocf_growth is not None and rev_growth > ocf_growth) else "pass"
    flags.append({"id": 2, "name": "Revenue vs Cash Collection Gap", "category": "Earnings Quality",
        "desc": "Revenue outpacing operating cash flow.", "status": status,
        "detail": f"Revenue growth: {fmt_pct(rev_growth)} | OCF growth: {fmt_pct(ocf_growth)}"})
    
    # 3. Gross margin movement
    gm1 = g("gross_profit",0) / g("revenue",0) if g("revenue",0) else 0
    gm3 = g("gross_profit",2) / g("revenue",2) if g("revenue",2) else 0
    gm_delta = gm3 - gm1
    status = "fail" if abs(gm_delta) > 0.10 else "caution" if abs(gm_delta) > 0.05 else "pass"
    flags.append({"id": 3, "name": "Unusual Gross Margin Movement", "category": "Earnings Quality",
        "desc": "Significant gross margin shift over the period.", "status": status,
        "detail": f"Gross margin Y1: {fmt_pct(gm1)} → Y3: {fmt_pct(gm3)} (Δ{fmt_pct(gm_delta)})"})
    
    # 4. DSO increasing
    dso1 = (g("ar",0) / g("revenue",0)) * 365 if g("revenue",0) else 0
    dso3 = (g("ar",2) / g("revenue",2)) * 365 if g("revenue",2) else 0
    status = "fail" if dso3 > dso1 * 1.3 and dso1 > 0 else "caution" if dso3 > dso1 * 1.1 and dso1 > 0 else "pass"
    flags.append({"id": 4, "name": "DSO Increasing (AR Buildup)", "category": "Working Capital",
        "desc": "Days Sales Outstanding rising — customers taking longer to pay.", "status": status,
        "detail": f"DSO Y1: {dso1:.0f} days → Y3: {dso3:.0f} days"})
    
    # 5. Inventory days
    inv1 = (g("inventory",0) / g("cogs",0)) * 365 if g("cogs",0) else 0
    inv3 = (g("inventory",2) / g("cogs",2)) * 365 if g("cogs",2) else 0
    status = "fail" if inv3 > inv1 * 1.3 and inv1 > 0 else "caution" if inv3 > inv1 * 1.1 and inv1 > 0 else "pass"
    flags.append({"id": 5, "name": "Inventory Days Increasing", "category": "Working Capital",
        "desc": "Inventory building faster than cost of sales.", "status": status,
        "detail": f"Inventory days Y1: {inv1:.0f} → Y3: {inv3:.0f}"})
    
    # 6. DPO stretching
    dpo1 = (g("ap",0) / g("cogs",0)) * 365 if g("cogs",0) else 0
    dpo3 = (g("ap",2) / g("cogs",2)) * 365 if g("cogs",2) else 0
    status = "caution" if dpo3 > dpo1 * 1.3 and dpo1 > 0 else "pass"
    flags.append({"id": 6, "name": "DPO Stretching (Supplier Squeeze)", "category": "Working Capital",
        "desc": "Paying suppliers slower — may indicate cash pressure.", "status": status,
        "detail": f"DPO Y1: {dpo1:.0f} days → Y3: {dpo3:.0f} days"})
    
    # 7. Cash conversion ratio
    ccr3 = g("ocf",2) / g("ebitda",2) if g("ebitda",2) else None
    status = "fail" if ccr3 is not None and ccr3 < 0.5 else "caution" if ccr3 is not None and ccr3 < 0.7 else "pass"
    flags.append({"id": 7, "name": "Low Cash Conversion (OCF/EBITDA)", "category": "Cash vs Profit",
        "desc": "Operating cash flow significantly below EBITDA.", "status": status,
        "detail": f"Cash Conversion Ratio Y3: {fmt_pct(ccr3)}"})
    
    # 8. Capex below D&A
    capex_ratio = g("capex",2) / g("da",2) if g("da",2) else None
    status = "fail" if capex_ratio is not None and capex_ratio < 0.5 else "caution" if capex_ratio is not None and capex_ratio < 0.8 else "pass"
    flags.append({"id": 8, "name": "Under-Investment (Capex < D&A)", "category": "Cash vs Profit",
        "desc": "Capital expenditure below depreciation — assets being milked.", "status": status,
        "detail": f"Capex/D&A Y3: {fmt_pct(capex_ratio)}"})
    
    # 9. Leverage
    lev1 = g("total_debt",0) / g("ebitda",0) if g("ebitda",0) else 0
    lev3 = g("total_debt",2) / g("ebitda",2) if g("ebitda",2) else 0
    status = "fail" if lev3 > 4 else "caution" if lev3 > 3 else "pass"
    flags.append({"id": 9, "name": "Leverage Increasing (Debt/EBITDA)", "category": "Leverage",
        "desc": "Net debt to EBITDA rising.", "status": status,
        "detail": f"Debt/EBITDA Y1: {lev1:.1f}x → Y3: {lev3:.1f}x"})
    
    # 10. Interest coverage
    icr3 = g("ebitda",2) / g("interest",2) if g("interest",2) else None
    status = "fail" if icr3 is not None and icr3 < 2 else "caution" if icr3 is not None and icr3 < 3 else "pass"
    flags.append({"id": 10, "name": "Interest Coverage Thinning", "category": "Leverage",
        "desc": "EBITDA barely covers interest — debt servicing risk.", "status": status,
        "detail": f"Interest Coverage Y3: {icr3:.1f}x" if icr3 else "Interest Coverage Y3: —"})
    
    # 11. Revenue growth inconsistency
    rg_y1y2 = pct_change(g("revenue",1), g("revenue",0))
    rg_y2y3 = pct_change(g("revenue",2), g("revenue",1))
    status = "caution" if rg_y1y2 is not None and rg_y2y3 is not None and abs((rg_y2y3 or 0) - (rg_y1y2 or 0)) > 0.15 else "pass"
    flags.append({"id": 11, "name": "Revenue Growth Inconsistency", "category": "Sustainability",
        "desc": "Growth rate changing dramatically year-over-year.", "status": status,
        "detail": f"Y1→Y2: {fmt_pct(rg_y1y2)} | Y2→Y3: {fmt_pct(rg_y2y3)}"})
    
    # 12. Cost cutting masking flat growth
    sga_pct1 = g("sga",0) / g("revenue",0) if g("revenue",0) else 0
    sga_pct3 = g("sga",2) / g("revenue",2) if g("revenue",2) else 0
    status = "caution" if sga_pct3 < sga_pct1 * 0.85 and rev_growth is not None and rev_growth < 0.1 else "pass"
    flags.append({"id": 12, "name": "Cost-Cutting Masking Flat Growth", "category": "Sustainability",
        "desc": "SG&A declining as % of revenue while revenue growth is weak.", "status": status,
        "detail": f"SG&A/Rev Y1: {fmt_pct(sga_pct1)} → Y3: {fmt_pct(sga_pct3)} | Rev growth: {fmt_pct(rev_growth)}"})
    
    # 13. Customer concentration
    top_conc = g("top1_revenue",2) / g("revenue",2) if g("revenue",2) else 0
    top5_conc = g("top5_revenue",2) / g("revenue",2) if g("revenue",2) else 0
    status = "fail" if top_conc > 0.25 else "caution" if top_conc > 0.15 or top5_conc > 0.6 else "pass"
    flags.append({"id": 13, "name": "Customer Concentration Risk", "category": "Concentration",
        "desc": "High dependency on a small number of customers.", "status": status,
        "detail": f"Top 1: {fmt_pct(top_conc)} | Top 5: {fmt_pct(top5_conc)} of revenue"})
    
    # 14. Related party
    rp_pct1 = g("related_party",0) / g("revenue",0) if g("revenue",0) else 0
    rp_pct3 = g("related_party",2) / g("revenue",2) if g("revenue",2) else 0
    status = "fail" if rp_pct3 > 0.1 else "caution" if rp_pct3 > 0.05 and rp_pct3 > rp_pct1 * 1.5 else "pass"
    flags.append({"id": 14, "name": "Related Party Transactions Growing", "category": "Governance",
        "desc": "Increasing related party activity.", "status": status,
        "detail": f"RP/Revenue Y1: {fmt_pct(rp_pct1)} → Y3: {fmt_pct(rp_pct3)}"})
    
    # 15. Cash erosion despite profitability
    cash_decline = g("cash",2) < g("cash",0) * 0.7
    profitable = g("net_profit",2) > 0 and g("net_profit",1) > 0
    status = "fail" if cash_decline and profitable else "caution" if g("cash",2) < g("cash",0) * 0.85 and profitable else "pass"
    flags.append({"id": 15, "name": "Cash Erosion Despite Profitability", "category": "Cash vs Profit",
        "desc": "Company is profitable but cash is declining.", "status": status,
        "detail": f"Cash Y1: {fmt_num(g('cash',0))} → Y3: {fmt_num(g('cash',2))} | Net Profit Y3: {fmt_num(g('net_profit',2))}"})
    
    return flags

# ── AI Narrative Generation ──────────────────────────────────────────
def generate_narrative(flags, company_name, currency):
    flag_summary = "\n".join([f"#{f['id']} {f['name']}: {f['status'].upper()} — {f['detail']}" for f in flags])
    
    prompt = f"""You are a senior finance advisor reviewing a company's financial health. Currency: {currency}. Company: {company_name or "the company"}.

Here are the results of 15 financial health signal tests:
{flag_summary}

Respond ONLY with a JSON object (no markdown, no backticks):
{{
  "overall_summary": "3-4 sentences summarizing the company's financial health — what's strong, what's concerning, overall trajectory",
  "signal_narratives": {{
    "1": "One sentence interpreting signal #1 and what it means for this specific company",
    "2": "...",
    "3": "...",
    "4": "...",
    "5": "...",
    "6": "...",
    "7": "...",
    "8": "...",
    "9": "...",
    "10": "...",
    "11": "...",
    "12": "...",
    "13": "...",
    "14": "...",
    "15": "..."
  }},
  "priority_actions": [
    "Most urgent action based on the worst signals — be specific and practical",
    "Second priority action",
    "Third priority action"
  ],
  "positive_signals": "1-2 sentences highlighting what's working well based on the healthy signals"
}}

Write like a CFO advisor briefing a founder. Be specific with numbers from the signals. No generic advice."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        st.error(f"AI narrative generation failed: {e}")
        return None

# ── PDF Extraction ───────────────────────────────────────────────────
def extract_from_pdf(pdf_bytes):
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    prompt = """You are extracting financial data from uploaded financial statements. Extract the following line items for 3 years (oldest to latest). If a value is not found, use 0.

Line items needed:
Revenue, COGS, Gross Profit, SGA, EBITDA, DA, Interest Expense, Net Profit,
Accounts Receivable, Inventory, Accounts Payable, Total Debt, Cash, Total Assets,
Operating Cash Flow, Capex,
Number of Customers, Revenue from Top Customer, Revenue from Top 5 Customers, Related Party Transactions

Respond ONLY with a JSON object. Keys must be exactly: revenue, cogs, gross_profit, sga, ebitda, da, interest, net_profit, ar, inventory, ap, total_debt, cash, total_assets, ocf, capex, num_customers, top1_revenue, top5_revenue, related_party.
Values are arrays of 3 numbers [year1_oldest, year2, year3_latest].
No markdown, no explanation. Just the JSON object."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        text = response.content[0].text
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        st.error(f"PDF extraction failed: {e}")
        return None

# ── Initialize session state ─────────────────────────────────────────
if "data" not in st.session_state:
    st.session_state.data = {k: [0, 0, 0] for k in ALL_KEYS}
if "step" not in st.session_state:
    st.session_state.step = "input"
if "narrative" not in st.session_state:
    st.session_state.narrative = None
if "company_name" not in st.session_state:
    st.session_state.company_name = ""
if "currency" not in st.session_state:
    st.session_state.currency = "USD"
if "pdf_processed" not in st.session_state:
    st.session_state.pdf_processed = False
if "csv_processed" not in st.session_state:
    st.session_state.csv_processed = False

# ── SIDEBAR ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### ⚙️ Settings")
    st.session_state.company_name = st.text_input("Company Name", st.session_state.company_name)
    st.session_state.currency = st.text_input("Currency", st.session_state.currency)
    
    st.divider()
    
    if st.button("📊 Load Sample Data", use_container_width=True):
        st.session_state.data = {k: list(v) for k, v in SAMPLE_DATA.items()}
        st.session_state.company_name = "Sample Corp"
        st.rerun()
    
    if st.button("🔄 Reset All", use_container_width=True):
        st.session_state.data = {k: [0, 0, 0] for k in ALL_KEYS}
        st.session_state.narrative = None
        st.session_state.step = "input"
        st.session_state.pdf_processed = False
        st.session_state.csv_processed = False
        st.rerun()
    
    st.divider()
    st.caption("Zehn Finance — AI in Finance Series")
    st.caption("This is a screening tool. It highlights patterns that may warrant further investigation — not a substitute for professional advisory.")

# ── STEP: Input ──────────────────────────────────────────────────────
if st.session_state.step == "input":
    
    # Check if data has been loaded (any non-zero values)
    has_data = any(any(v != 0 for v in st.session_state.data[k]) for k in ALL_KEYS)
    
    if not has_data:
        st.markdown("#### Choose how to upload your financial data")
        st.markdown("")
    
    # Upload options
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📄 Upload Financial Statements")
        st.caption("PDF — Annual reports, audited financials, or management accounts")
        pdf_file = st.file_uploader("Upload PDF", type=["pdf"], key="pdf_upload", label_visibility="collapsed")
        if pdf_file and not st.session_state.get("pdf_processed"):
            with st.spinner("Extracting data with AI — this may take a moment..."):
                extracted = extract_from_pdf(pdf_file.read())
                if extracted:
                    for key in ALL_KEYS:
                        if key in extracted and isinstance(extracted[key], list):
                            st.session_state.data[key] = [float(v) for v in extracted[key]]
                    st.session_state.pdf_processed = True
                    st.rerun()
    
    with col2:
        st.markdown("#### 📊 Upload Filled Template")
        st.caption("CSV — Download template below, fill in your numbers, upload back")
        csv_file = st.file_uploader("Upload CSV", type=["csv"], key="csv_upload", label_visibility="collapsed")
        if csv_file and not st.session_state.get("csv_processed"):
            try:
                df = pd.read_csv(csv_file)
                mapping = {
                    "Revenue": "revenue", "Cost of Goods Sold (COGS)": "cogs", "Gross Profit": "gross_profit",
                    "SG&A / Operating Expenses": "sga", "EBITDA": "ebitda", "Depreciation & Amortization": "da",
                    "Interest Expense": "interest", "Net Profit": "net_profit",
                    "Accounts Receivable (AR)": "ar", "Inventory": "inventory", "Accounts Payable (AP)": "ap",
                    "Total Debt": "total_debt", "Cash & Equivalents": "cash", "Total Assets": "total_assets",
                    "Operating Cash Flow (OCF)": "ocf", "Capital Expenditure (Capex)": "capex",
                    "Number of Customers": "num_customers", "Revenue from Top Customer": "top1_revenue",
                    "Revenue from Top 5 Customers": "top5_revenue", "Related Party Transactions": "related_party",
                }
                for _, row in df.iterrows():
                    label = str(row.iloc[0]).strip()
                    key = mapping.get(label)
                    if key:
                        st.session_state.data[key] = [safe(row.iloc[1]), safe(row.iloc[2]), safe(row.iloc[3])]
                st.session_state.csv_processed = True
                st.rerun()
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")
        
        # Download template button
        template_csv = "Line Item,Year 1 (Oldest),Year 2,Year 3 (Latest)\n"
        template_rows = [
            "Revenue,,,,", "Cost of Goods Sold (COGS),,,,", "Gross Profit,,,,",
            "SG&A / Operating Expenses,,,,", "EBITDA,,,,", "Depreciation & Amortization,,,,",
            "Interest Expense,,,,", "Net Profit,,,,",
            "Accounts Receivable (AR),,,,", "Inventory,,,,", "Accounts Payable (AP),,,,",
            "Total Debt,,,,", "Cash & Equivalents,,,,", "Total Assets,,,,",
            "Operating Cash Flow (OCF),,,,", "Capital Expenditure (Capex),,,,",
            "Number of Customers,,,,", "Revenue from Top Customer,,,,",
            "Revenue from Top 5 Customers,,,,", "Related Party Transactions,,,,"
        ]
        template_csv += "\n".join(template_rows)
        st.download_button(
            label="⬇️ Download Blank Template (CSV)",
            data=template_csv,
            file_name="Financial_Pulse_Check_Template.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    # If data is loaded, show summary + Run button
    if has_data:
        st.divider()
        st.success("✅ Financial data loaded successfully. Review the summary and click **Run Pulse Check**.")
        
        # Full data review table
        review_data = []
        for section, items in LINE_ITEMS.items():
            for key, label in items:
                review_data.append({
                    "Section": section,
                    "Line Item": label,
                    "Year 1": fmt_num(st.session_state.data[key][0]),
                    "Year 2": fmt_num(st.session_state.data[key][1]),
                    "Year 3": fmt_num(st.session_state.data[key][2]),
                })
        
        review_df = pd.DataFrame(review_data)
        st.dataframe(review_df, use_container_width=True, hide_index=True, height=400)
        
        st.markdown("")
        if st.button("🔍 Run Pulse Check →", type="primary", use_container_width=True):
            st.session_state.step = "results"
            st.rerun()

# ── STEP: Results ────────────────────────────────────────────────────
elif st.session_state.step == "results":
    
    data = st.session_state.data
    flags = run_signals(data)
    
    fail_count = sum(1 for f in flags if f["status"] == "fail")
    caution_count = sum(1 for f in flags if f["status"] == "caution")
    pass_count = sum(1 for f in flags if f["status"] == "pass")
    
    overall = "CRITICAL" if fail_count >= 5 else "ELEVATED" if fail_count >= 3 or (fail_count + caution_count) >= 6 else "MODERATE" if fail_count >= 1 or caution_count >= 3 else "STRONG"
    overall_color = {"CRITICAL": RED, "ELEVATED": AMBER, "MODERATE": GOLD, "STRONG": GREEN}[overall]
    overall_bg = {"CRITICAL": LT_RED, "ELEVATED": LT_AMBER, "MODERATE": "#FFFBF0", "STRONG": LT_GREEN}[overall]
    
    # Overall badge
    company = st.session_state.company_name or "Company"
    st.markdown(f"""
    <div style="background:{overall_bg}; border:2px solid {overall_color}; border-radius:12px; padding:20px 24px; margin-bottom:20px; display:flex; align-items:center; gap:20px;">
        <div style="width:80px; height:80px; border-radius:50%; background:{overall_color}; display:flex; align-items:center; justify-content:center; color:white; font-weight:800; font-size:13px; text-align:center; line-height:1.2; flex-shrink:0;">
            {overall}<br/>PULSE
        </div>
        <div style="flex:1;">
            <div style="font-size:20px; font-weight:700; color:{overall_color}; margin-bottom:4px;">{company} — Financial Pulse: {overall}</div>
            <div style="font-size:14px; color:#555;">{fail_count} signals need attention, {caution_count} to watch, {pass_count} healthy — across 15 financial health checks.</div>
        </div>
        <div style="display:flex; gap:20px; flex-shrink:0;">
            <div style="text-align:center;"><div style="font-size:26px; font-weight:700; color:{RED};">{fail_count}</div><div style="font-size:11px; color:#888;">ATTENTION</div></div>
            <div style="text-align:center;"><div style="font-size:26px; font-weight:700; color:{AMBER};">{caution_count}</div><div style="font-size:11px; color:#888;">WATCH</div></div>
            <div style="text-align:center;"><div style="font-size:26px; font-weight:700; color:{GREEN};">{pass_count}</div><div style="font-size:11px; color:#888;">HEALTHY</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Generate AI Narrative
    if st.session_state.narrative is None:
        with st.spinner("Generating AI-powered insights and recommendations..."):
            st.session_state.narrative = generate_narrative(flags, company, st.session_state.currency)
    
    narrative = st.session_state.narrative
    
    # AI Summary + Actions
    if narrative:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 📋 Overall Assessment")
            st.markdown(narrative.get("overall_summary", ""))
            if narrative.get("positive_signals"):
                st.success(f"**What's Working:** {narrative['positive_signals']}")
        
        with col2:
            st.markdown("#### 🎯 Priority Actions")
            for i, action in enumerate(narrative.get("priority_actions", []), 1):
                st.markdown(f"**{i}.** {action}")
    
    st.divider()
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📈 3-Year Trend")
        trend_df = pd.DataFrame({
            "Year": ["Year 1", "Year 2", "Year 3"],
            "Revenue": [safe(data["revenue"][i]) for i in range(3)],
            "EBITDA": [safe(data["ebitda"][i]) for i in range(3)],
            "OCF": [safe(data["ocf"][i]) for i in range(3)],
            "Net Profit": [safe(data["net_profit"][i]) for i in range(3)],
        })
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=trend_df["Year"], y=trend_df["Revenue"], name="Revenue", line=dict(color=NAVY, width=3)))
        fig.add_trace(go.Scatter(x=trend_df["Year"], y=trend_df["EBITDA"], name="EBITDA", line=dict(color=GOLD, width=2)))
        fig.add_trace(go.Scatter(x=trend_df["Year"], y=trend_df["OCF"], name="OCF", line=dict(color=GREEN, width=2)))
        fig.add_trace(go.Scatter(x=trend_df["Year"], y=trend_df["Net Profit"], name="Net Profit", line=dict(color=RED, width=2, dash="dash")))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("#### 🏷️ Signals by Category")
        cat_data = {}
        for f in flags:
            cat = f["category"]
            if cat not in cat_data:
                cat_data[cat] = {"Needs Attention": 0, "Watch": 0, "Healthy": 0}
            label_map = {"fail": "Needs Attention", "caution": "Watch", "pass": "Healthy"}
            cat_data[cat][label_map[f["status"]]] += 1
        
        cat_df = pd.DataFrame([{"Category": k, **v} for k, v in cat_data.items()])
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(y=cat_df["Category"], x=cat_df["Needs Attention"], name="Needs Attention", orientation="h", marker_color=RED))
        fig2.add_trace(go.Bar(y=cat_df["Category"], x=cat_df["Watch"], name="Watch", orientation="h", marker_color=AMBER))
        fig2.add_trace(go.Bar(y=cat_df["Category"], x=cat_df["Healthy"], name="Healthy", orientation="h", marker_color=GREEN))
        fig2.update_layout(barmode="stack", height=300, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig2, use_container_width=True)
    
    st.divider()
    
    # 15 Signals detail
    st.markdown("#### 🔍 15 Health Signals — Detailed Results")
    
    status_emoji = {"pass": "💚", "caution": "🟡", "fail": "🔴"}
    status_label = {"pass": "HEALTHY", "caution": "WATCH", "fail": "NEEDS ATTENTION"}
    signal_narratives = narrative.get("signal_narratives", {}) if narrative else {}
    
    for f in flags:
        css_class = f"signal-{f['status']}"
        emoji = status_emoji[f["status"]]
        label = status_label[f["status"]]
        narr = signal_narratives.get(str(f["id"]), "")
        
        narr_html = f'<div class="narrative-box">💡 {narr}</div>' if narr else ""
        
        st.markdown(f"""
        <div class="{css_class}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <span style="font-size:15px;">{emoji}</span>
                    <strong style="color:{NAVY};">#{f['id']} {f['name']}</strong>
                    <span style="font-size:11px; padding:2px 8px; border-radius:4px; font-weight:600; margin-left:8px;
                        background:{'#FDF2F2' if f['status']=='fail' else '#FFF8ED' if f['status']=='caution' else '#EAF7EE'};
                        color:{RED if f['status']=='fail' else AMBER if f['status']=='caution' else GREEN};">{label}</span>
                    <br/>
                    <span style="font-size:13px; color:#555;">{f['desc']}</span><br/>
                    <code style="font-size:12px; color:#888;">{f['detail']}</code>
                    {narr_html}
                </div>
                <span style="font-size:11px; color:#999; white-space:nowrap;">{f['category']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # Back button
    if st.button("← Back to Input", use_container_width=True):
        st.session_state.step = "input"
        st.session_state.narrative = None
        st.rerun()
