"""
apps/cashbook.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Cashbook
══════════════════════════════════════════════════════════════════════

Bare cash-in / cash-out ledger. Deliberately NOT a capital/equity tracker —
it answers "where did my cash go", not "is my capital being eroded". See
shared/db.py's cashbook helpers for how entries are mirrored in from
sales, expenses, restocks, and debt collections.

  • Daily Ledger — opening/closing balance for a selected date range,
    filterable by payment method, entry type visible on every row so a
    restock (money converting to stock) never looks identical to an
    expense (money actually spent).
  • Manual Entry — for cash movements that aren't a sale/expense/restock/
    debt collection: owner drawings, capital top-ups, bank deposits, etc.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from shared.db import (
    get_cashbook_df, log_cashbook_entry, compute_cashbook_summary,
    db_delete, TBL_CASHBOOK,
    fmt_naira, safe_float,
)
from shared.theme import apply_suite_css, kpi_card, section_header, page_header

_PAYMENT_METHODS = ["Cash", "Bank Transfer", "POS", "Mobile Money"]
_ENTRY_TYPE_ICONS = {
    "Sale":            "🛒",
    "Expense":         "💸",
    "Restock":         "📦",
    "Debt Collection": "📕",
    "Manual":          "✍️",
}


def page_cashbook():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📒 Cashbook", "Every cedi/naira in and out — and what's left")

    df = get_cashbook_df(business_id)

    tab1, tab2 = st.tabs(["📖 Daily Ledger", "➕ Manual Entry"])

    # ══════════════════════
    # Tab 1 — Daily Ledger
    # ══════════════════════
    with tab1:
        _page_daily_ledger(df, business_id)

    # ══════════════════════
    # Tab 2 — Manual Entry
    # ══════════════════════
    with tab2:
        _page_manual_entry(business_id, user)

    if "cbk_msg" in st.session_state:
        msg = st.session_state.pop("cbk_msg")
        (st.success if msg.startswith("✅") else st.error)(msg)


# ══════════════════════════════════════════════════════════════════════════════
# DAILY LEDGER
# ══════════════════════════════════════════════════════════════════════════════

def _page_daily_ledger(df: pd.DataFrame, business_id: str):
    if df.empty:
        st.info(
            "No cashbook entries yet. Entries appear automatically as you "
            "record sales, expenses, restocks, and debt collections — or "
            "log one manually in the **Manual Entry** tab."
        )
        return

    dc1, dc2, dc3 = st.columns([1, 1, 1.4])
    start_date = dc1.date_input(
        "From", value=datetime.now().date() - timedelta(days=6), key="cbk_start"
    )
    end_date = dc2.date_input(
        "To", value=datetime.now().date(), key="cbk_end"
    )
    method_filter = dc3.multiselect(
        "Payment Method", _PAYMENT_METHODS, default=_PAYMENT_METHODS, key="cbk_method_filter"
    )

    if start_date > end_date:
        st.error("‘From’ date must be before ‘To’ date.")
        return

    summary = compute_cashbook_summary(df, start_date, end_date)

    section_header("Balance for this period")
    k1, k2, k3, k4 = st.columns(4)
    with k1: kpi_card("Opening Balance", fmt_naira(summary["opening"]), icon="🌅")
    with k2: kpi_card("Cash In", fmt_naira(summary["total_in"]), positive=True, icon="⬆️")
    with k3: kpi_card("Cash Out", fmt_naira(summary["total_out"]), positive=False, icon="⬇️")
    with k4:
        closing = summary["closing"]
        kpi_card(
            "Closing Balance", fmt_naira(closing),
            positive=(closing >= summary["opening"]), icon="🌇",
        )

    st.markdown("---")
    section_header("Ledger")

    d = df.copy()
    d["_date"] = d["entry_date"].dt.date
    windowed = d[(d["_date"] >= start_date) & (d["_date"] <= end_date)]
    if method_filter:
        windowed = windowed[windowed["payment_method"].isin(method_filter)]

    if windowed.empty:
        st.info("No entries in this date range / payment method selection.")
        return

    # Running balance computed at render time — starts from the opening
    # balance for the window, cumulative sum of signed_amount going forward.
    # Recomputed every render rather than stored, so an edited/deleted entry
    # (e.g. a voided sale) never leaves a stale balance behind.
    windowed = windowed.sort_values("entry_date").copy()
    windowed["running_balance"] = summary["opening"] + windowed["signed_amount"].cumsum()

    for _, r in windowed.sort_values("entry_date", ascending=False).iterrows():
        icon      = _ENTRY_TYPE_ICONS.get(r["entry_type"], "•")
        sign      = "+" if r["direction"] == "In" else "−"
        amt_color = "kpi-positive" if r["direction"] == "In" else "kpi-negative"
        rb        = windowed.loc[windowed["entry_id"] == r["entry_id"], "running_balance"].iloc[0]
        st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center;
            padding:0.6rem 0.9rem; border-bottom:1px solid var(--border);">
  <div>
    <span style="font-size:1.05rem;">{icon}</span>
    <strong style="margin-left:6px;">{r['entry_type']}</strong>
    <span style="color:var(--text-secondary); margin-left:8px; font-size:0.85rem;">
      {r['entry_date'].strftime('%d %b %Y')} · {r['payment_method']}
    </span>
    {f'<div style="font-size:0.8rem; color:var(--text-secondary); margin-top:2px;">{r["note"]}</div>' if r.get("note") else ""}
  </div>
  <div style="text-align:right;">
    <div class="{amt_color}" style="font-weight:700;">{sign} {fmt_naira(r['amount'])}</div>
    <div style="font-size:0.75rem; color:var(--text-secondary);">Bal: {fmt_naira(rb)}</div>
  </div>
</div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MANUAL ENTRY
# ══════════════════════════════════════════════════════════════════════════════

def _page_manual_entry(business_id: str, user: dict):
    st.caption(
        "For cash movements that aren't a sale, expense, restock, or debt "
        "collection — e.g. money you put into or took out of the business, "
        "or a bank deposit/withdrawal."
    )
    with st.form("cbk_manual_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        direction = c1.selectbox("Direction", ["In", "Out"])
        amount    = c2.number_input(
            "Amount (" + st.session_state.get("currency_symbol", "₦") + ") *",
            min_value=0.0, step=100.0,
        )
        entry_date     = c1.date_input("Date", value=datetime.now().date())
        payment_method = c2.selectbox("Payment Method", _PAYMENT_METHODS)
        note = st.text_input(
            "Note *", placeholder="e.g. Owner drawing for personal use / Capital top-up"
        )
        submitted = st.form_submit_button("Log Entry", width="stretch", type="primary")

    if submitted:
        if amount <= 0 or not note.strip():
            st.error("Please enter a valid amount and a note describing this entry.")
            return
        ok = log_cashbook_entry(
            business_id=business_id, entry_date=entry_date,
            entry_type="Manual", direction=direction,
            amount=amount, payment_method=payment_method,
            note=note.strip(),
            recorded_by=user.get("full_name", user.get("email", "")),
        )
        st.session_state["cbk_msg"] = (
            f"✅ Logged: {direction} {fmt_naira(amount)} — {note.strip()}"
            if ok else "❌ Failed to log entry."
        )
        st.rerun()
