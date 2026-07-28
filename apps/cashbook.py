"""
apps/cashbook.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Cashbook
══════════════════════════════════════════════════════════════════════

Bare cash-in / cash-out ledger. Deliberately NOT a capital/equity tracker —
it answers "where did my cash go", not "is my capital being eroded". See
shared/db.py's cashbook helpers for how entries are mirrored in from
sales, expenses, restocks, and debt collections.

  • Snapshot — one live dashboard card: balance + delta, cash in/out,
    a payment-method composition bar ("where the cash sits"), entry-type
    chips for the period, and recent activity — all in one glance,
    recomputed fresh every render (no manual refresh, no stale cache —
    every sale/expense/restock/debt-payment write clears the cashbook
    cache the instant it happens). Defaults to Today; This Week / This
    Month / Custom available. A "View full ledger" expander underneath
    holds the detailed row-by-row feed for anyone who wants to drill in.
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
from shared.theme import apply_suite_css, page_header

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

    # No caching gap for the person reading this: get_cashbook_df() pulls
    # fresh on every rerun (its cache is cleared the instant any sale,
    # expense, restock, or debt payment mirrors an entry in), so this
    # dashboard is always current as of the moment it renders — never a
    # stale, manually-refreshed snapshot.
    df = get_cashbook_df(business_id)

    tab1, tab2 = st.tabs(["📊 Snapshot", "➕ Manual Entry"])

    # ══════════════════════
    # Tab 1 — Snapshot
    # ══════════════════════
    with tab1:
        _page_snapshot(df, business_id)

    # ══════════════════════
    # Tab 2 — Manual Entry
    # ══════════════════════
    with tab2:
        _page_manual_entry(business_id, user)

    if "cbk_msg" in st.session_state:
        msg = st.session_state.pop("cbk_msg")
        (st.success if msg.startswith("✅") else st.error)(msg)


# ══════════════════════════════════════════════════════════════════════════════
# SNAPSHOT — one live dashboard card: balance, in/out, method split, recent activity
# ══════════════════════════════════════════════════════════════════════════════

def _page_snapshot(df: pd.DataFrame, business_id: str):
    if df.empty:
        st.info(
            "No cashbook entries yet. Entries appear automatically as you "
            "record sales, expenses, restocks, and debt collections — or "
            "log one manually in the **Manual Entry** tab."
        )
        return

    dc1, dc2 = st.columns([1.3, 1.7])
    period = dc1.selectbox(
        "Period", ["Today", "This Week", "This Month", "Custom"], key="cbk_period"
    )
    today = datetime.now().date()
    if period == "Today":
        start_date, end_date = today, today
    elif period == "This Week":
        start_date, end_date = today - timedelta(days=today.weekday()), today
    elif period == "This Month":
        start_date, end_date = today.replace(day=1), today
    else:
        c1, c2 = dc2.columns(2)
        start_date = c1.date_input("From", value=today, key="cbk_start")
        end_date   = c2.date_input("To", value=today, key="cbk_end")

    method_filter = dc2.multiselect(
        "Payment method", _PAYMENT_METHODS, default=_PAYMENT_METHODS,
        key="cbk_method_filter",
    ) if period != "Custom" else _PAYMENT_METHODS

    if start_date > end_date:
        st.error("‘From’ date must be before ‘To’ date.")
        return

    d = df.copy()
    d["_date"] = d["entry_date"].dt.date
    windowed_all_methods = d[(d["_date"] >= start_date) & (d["_date"] <= end_date)]
    windowed = windowed_all_methods[windowed_all_methods["payment_method"].isin(method_filter)] \
        if method_filter else windowed_all_methods

    summary = compute_cashbook_summary(df, start_date, end_date)
    delta   = round(summary["closing"] - summary["opening"], 2)
    delta_positive = delta >= 0

    # "Where the cash sits" — true cumulative balance per payment method,
    # as of end_date, using the FULL history (not just this window) so it
    # reflects the actual composition of the balance, not just this
    # period's inflows. Deliberately NOT clipped at zero — if restocking
    # or expenses paid via a given method outpaced cash-in through that
    # same method, that method's balance is genuinely negative and needs
    # to show as such, not get silently zeroed into invisibility.
    upto = d[d["_date"] <= end_date]
    method_balances = (
        upto.groupby("payment_method")["signed_amount"].sum()
        if not upto.empty else pd.Series(dtype=float)
    )
    method_total = method_balances.sum()  # equals summary["closing"]
    shortfall_methods = [m for m in _PAYMENT_METHODS if method_balances.get(m, 0) < 0]

    _method_colors = {
        "Cash": "#F5A623", "Bank Transfer": "#3B82C4",
        "POS": "#00C896", "Mobile Money": "#FF4D6D",
    }
    bar_segments, legend_items = "", ""
    # A composition bar only makes sense when the overall balance is
    # positive — percentages of a zero/negative total can't be drawn as
    # proportional widths. When the balance itself is negative, the big
    # red number above already carries that signal; no bar is more honest
    # here than a misleading one.
    if method_total > 0:
        for m in _PAYMENT_METHODS:
            amt = method_balances.get(m, 0)
            if amt <= 0:
                continue
            pct = round((amt / method_total) * 100, 1)
            color = _method_colors.get(m, "#8BA0B8")
            bar_segments += f'<div style="width:{pct}%; background:{color};"></div>'
            legend_items += (
                f'<span style="font-size:0.72rem; color:var(--text-secondary); margin-right:12px;">'
                f'<span style="display:inline-block; width:7px; height:7px; border-radius:2px; '
                f'background:{color}; margin-right:4px;"></span>{m} {pct}%</span>'
            )

    # Entry-type composition for the period — cash-out types especially,
    # so a restock (money → stock) is never confused with real spend.
    type_chips = ""
    if not windowed.empty:
        by_type = windowed.groupby(["entry_type", "direction"])["amount"].sum()
        for etype in ["Sale", "Expense", "Restock", "Debt Collection", "Manual"]:
            total = 0
            for dirn in ("In", "Out"):
                total += by_type.get((etype, dirn), 0)
            if total <= 0:
                continue
            icon = _ENTRY_TYPE_ICONS.get(etype, "•")
            type_chips += (
                f'<span style="font-size:0.75rem; background:var(--surface2); '
                f'border-radius:8px; padding:4px 10px; margin:0 6px 6px 0; display:inline-block;">'
                f'{icon} {etype}: {fmt_naira(total)}</span>'
            )

    # Recent activity — last 4 entries within the selected window.
    recent_html = ""
    if not windowed.empty:
        for _, r in windowed.sort_values("entry_date", ascending=False).head(4).iterrows():
            icon  = _ENTRY_TYPE_ICONS.get(r["entry_type"], "•")
            sign  = "+" if r["direction"] == "In" else "−"
            color = "var(--jade)" if r["direction"] == "In" else "var(--ruby)"
            recent_html += f"""
<div style="display:flex; justify-content:space-between; padding:5px 0; font-size:0.85rem;">
  <span>{icon} {r['note'] or r['entry_type']}</span>
  <span style="color:{color}; font-weight:600;">{sign} {fmt_naira(r['amount'])}</span>
</div>"""
    else:
        recent_html = (
            '<div style="font-size:0.85rem; color:var(--text-secondary); padding:5px 0;">'
            'No entries in this period / method selection.</div>'
        )

    delta_color = "var(--jade)" if delta_positive else "var(--ruby)"
    delta_arrow = "↑" if delta_positive else "↓"

    st.markdown(f"""
<div style="background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:1.25rem 1.4rem;">
  <div style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.4rem;">
    Cash balance · {period.lower() if period != "Custom" else f"{start_date} to {end_date}"}
  </div>
  <div style="font-family:var(--font-display); font-size:1.9rem; font-weight:800;
              color:var(--text-primary); line-height:1.15; word-break:break-word;">
    {fmt_naira(summary['closing'])}
  </div>
  <div style="font-size:0.78rem; color:var(--text-muted); margin-bottom:1rem;">
    <span style="color:{delta_color}; font-weight:700;">{delta_arrow} {fmt_naira(abs(delta))}</span>
    &nbsp;·&nbsp;Opening {fmt_naira(summary['opening'])}
  </div>

  <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:1.1rem;">
    <div style="background:var(--jade-dim); border-radius:10px; padding:0.7rem 0.85rem;">
      <div style="font-size:0.72rem; color:var(--jade);">⬇️ In</div>
      <div style="font-size:1.1rem; font-weight:700; color:var(--jade);">{fmt_naira(summary['total_in'])}</div>
    </div>
    <div style="background:var(--ruby-dim); border-radius:10px; padding:0.7rem 0.85rem;">
      <div style="font-size:0.72rem; color:var(--ruby);">⬆️ Out</div>
      <div style="font-size:1.1rem; font-weight:700; color:var(--ruby);">{fmt_naira(summary['total_out'])}</div>
    </div>
  </div>

  {"".join([
    '<div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:6px;">Where the cash sits</div>',
    f'<div style="display:flex; height:8px; border-radius:4px; overflow:hidden; margin-bottom:6px;">{bar_segments}</div>',
    f'<div style="margin-bottom:1rem;">{legend_items}</div>',
  ]) if method_total > 0 else ''}

  {f'''<div style="background:var(--ruby-dim); color:var(--ruby); border-radius:8px;
              padding:0.5rem 0.75rem; font-size:0.75rem; margin-bottom:0.9rem;">
    ⚠️ {", ".join(shortfall_methods)} balance{"s are" if len(shortfall_methods) > 1 else " is"} negative —
    more paid out via that method than received.
  </div>''' if shortfall_methods else ''}

  {f'<div style="margin-bottom:0.9rem;">{type_chips}</div>' if type_chips else ''}

  <div style="border-top:1px solid var(--border); padding-top:0.75rem;">
    <div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:4px;">Recent</div>
    {recent_html}
  </div>
</div>
    """, unsafe_allow_html=True)

    with st.expander("View full ledger for this period"):
        if windowed.empty:
            st.caption("No entries to show.")
        else:
            full = windowed.sort_values("entry_date").copy()
            full["running_balance"] = summary["opening"] + full["signed_amount"].cumsum()
            for _, r in full.sort_values("entry_date", ascending=False).iterrows():
                icon      = _ENTRY_TYPE_ICONS.get(r["entry_type"], "•")
                sign      = "+" if r["direction"] == "In" else "−"
                amt_color = "kpi-positive" if r["direction"] == "In" else "kpi-negative"
                rb        = full.loc[full["entry_id"] == r["entry_id"], "running_balance"].iloc[0]
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
