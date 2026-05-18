# ============================================================
#  utils.py — Pure utility helpers (no Streamlit dependencies)
# ============================================================

import uuid
import re
import streamlit as st
from datetime import datetime
from dateutil import parser as dateparser


def gen_id(prefix="") -> str:
    """Generate a short unique ID with optional prefix."""
    return f"{prefix}{uuid.uuid4().hex[:10].upper()}"


def fmt_naira(amount) -> str:
    """Format a number as Nigerian Naira string."""
    try:
        return f"\u20a6{float(amount):,.2f}"
    except Exception:
        return "\u20a60.00"


def safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def safe_int(val, default=0) -> int:
    try:
        return int(val)
    except Exception:
        return default


def parse_date(val):
    """Parse a date string to datetime. Returns None on failure."""
    try:
        return dateparser.parse(str(val))
    except Exception:
        return None


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email))


# ─────────────────────────────────────────────
#  UI COMPONENT HELPERS
# ─────────────────────────────────────────────

def kpi_card(label: str, value: str, sub: str = "", positive=None):
    sub_class = ""
    if positive is True:
        sub_class = "kpi-positive"
    elif positive is False:
        sub_class = "kpi-negative"
    st.markdown(f"""
<div class="kpi-card">
<div class="kpi-label">{label}</div>
<div class="kpi-value">{value}</div>
{f'<div class="kpi-sub {sub_class}">{sub}</div>' if sub else ""}
</div>
    """, unsafe_allow_html=True)


def section_header(title: str):
    st.markdown(f"""
<div style="
font-family:'Syne',sans-serif;
font-size:0.95rem;font-weight:700;
color:#F0F4F8;letter-spacing:-0.01em;
margin:1.75rem 0 0.875rem 0;
padding-bottom:0.5rem;
border-bottom:1px solid #1F2D3D;
display:flex;align-items:center;gap:0.5rem;
">
<span style="
display:inline-block;width:3px;height:16px;
background:#F5A623;border-radius:2px;flex-shrink:0;
"></span>
{title}
</div>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    now_str = datetime.now().strftime("%A, %d %B %Y")
    st.markdown(f"""
<div style="
display:flex;justify-content:space-between;align-items:flex-start;
margin-bottom:1.5rem;padding-bottom:1rem;
border-bottom:2px solid #1F2D3D;
">
<div>
<div style="font-family:'Syne',sans-serif;font-size:1.75rem;
font-weight:800;color:#F0F4F8;letter-spacing:-0.03em;
margin-bottom:0.2rem;">{title}</div>
{f'<div style="font-size:0.875rem;color:#8BA0B8;">{subtitle}</div>' if subtitle else ""}
</div>
<div style="font-size:0.78rem;color:#4A6080;text-align:right;
padding-top:0.3rem;">{now_str}</div>
</div>
    """, unsafe_allow_html=True)


def stock_pill(qty: int, reorder: int) -> str:
    if qty <= 0:
        return '<span class="stock-critical">Out of Stock</span>'
    elif qty <= reorder:
        return f'<span class="stock-low">Low: {qty}</span>'
    return f'<span class="stock-ok">{qty} in stock</span>'
