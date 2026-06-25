"""
pages/health.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Business Health App
══════════════════════════════════════════════════════════════════════

Pages contained in this module:
  • Expenses       — log, view, edit, delete expenses with charts
  • Insights       — monthly trends, product analysis, export
  • Admin Panel    — platform management (admin role only)

Cross-app links:
  • compute_kpis pulls both sales + expenses → net profit card
  • compute_insights pulls sales + products → stockout, slow movers
"""

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shared.db import (
    get_sales_df, get_products_df, get_expenses_df,
    compute_kpis, compute_insights,
    db_fetch, db_insert, db_update, db_delete,
    get_payments_df, log_payment,
    get_debts_df, get_debt_payments_df, record_debt_payment,
    get_sale_items_df,
    TBL_USERS, TBL_EXPENSES, TBL_PAYMENTS, TBL_SALE_ITEMS,
    TBL_DEBTS, TBL_ACTIVITY,
    PAYMENT_DETAILS,
    gen_id, fmt_naira, safe_float, safe_int, parse_date,
    get_supabase,
)
from shared.theme import (
    apply_suite_css, kpi_card, section_header, page_header,
)


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSES
# ══════════════════════════════════════════════════════════════════════════════

def page_expenses():
    apply_suite_css()
    apply_theme_mode()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("💸 Expense Tracker", "Log and monitor your business expenses")

    # ── Persistent status message (survives rerun) ──
    if "exp_log_msg" in st.session_state:
        _msg = st.session_state.pop("exp_log_msg")
        st.success(_msg)

    tab1, tab2 = st.tabs(["📋 View Expenses", "➕ Log Expense"])

    # ══════════════════════
    # Tab 1 — View
    # ══════════════════════
    with tab1:
        expenses_df = get_expenses_df(business_id)
        if expenses_df.empty:
            st.info("No expenses logged yet.")
        else:
            col1, col2 = st.columns(2)
            start_date = col1.date_input("From", value=(datetime.now() - timedelta(days=30)).date())
            end_date   = col2.date_input("To",   value=datetime.now().date())

            filtered = expenses_df[
                (expenses_df["expense_date"].dt.date >= start_date) &
                (expenses_df["expense_date"].dt.date <= end_date)
            ]

            c1, c2, c3 = st.columns(3)
            with c1:
                kpi_card("Total Expenses", fmt_naira(filtered["amount"].sum()),
                         "In selected period", icon="💸")
            with c2:
                kpi_card("Transactions", str(len(filtered)), "Expense entries", icon="🧾")
            with c3:
                avg = filtered["amount"].mean() if not filtered.empty else 0
                kpi_card("Average Expense", fmt_naira(avg), "Per entry", icon="📊")

            if not filtered.empty:
                # Category breakdown chart
                cat_breakdown = (
                    filtered.groupby("category")["amount"]
                    .sum().reset_index()
                    .sort_values("amount", ascending=False)
                )
                if not cat_breakdown.empty:
                    with st.expander("📊 Expenses by Category", expanded=True):
                        fig = px.bar(
                            cat_breakdown, x="category", y="amount",
                            labels={"amount": "Amount (₦)", "category": "Category"},
                            color_discrete_sequence=["#ef4444"],
                        )
                        fig.update_layout(
                            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=0, r=0, t=10, b=0), height=280,
                        )
                        st.plotly_chart(fig, width='stretch')

                # Search
                exp_search = st.text_input("🔍 Search expenses", key="exp_search",
                                           placeholder="Filter by description…")
                if exp_search:
                    filtered = filtered[
                        filtered["description"].str.contains(exp_search, case=False, na=False)
                    ]

                # Pagination
                EXP_PAGE  = 20
                exp_pages = max(1, -(-len(filtered) // EXP_PAGE))
                if "exp_page" not in st.session_state:
                    st.session_state.exp_page = 1
                exp_pg     = st.session_state.exp_page
                page_slice = filtered.sort_values("expense_date", ascending=False)
                page_slice = page_slice.iloc[(exp_pg-1)*EXP_PAGE: exp_pg*EXP_PAGE]

                st.caption(f"Showing {len(page_slice)} of {len(filtered)} entries  •  Page {exp_pg} of {exp_pages}")
                st.markdown("---")

                for _, r in page_slice.iterrows():
                    exp_id = r["expense_id"]
                    with st.expander(
                        f"**{r['description']}** | {r['category']} | "
                        f"{fmt_naira(r['amount'])} | "
                        f"{r['expense_date'].strftime('%d %b %Y') if pd.notna(r['expense_date']) else ''}",
                        expanded=False,
                    ):
                        _EXP_CATS = ["Rent","Utilities","Salaries","Supplies","Transport",
                                     "Marketing","Maintenance","Taxes","Miscellaneous"]
                        with st.form(f"edit_exp_{exp_id}"):
                            ef1, ef2   = st.columns(2)
                            new_name   = ef1.text_input("Description", value=r["description"])
                            cat_idx    = _EXP_CATS.index(r["category"]) if r["category"] in _EXP_CATS else 0
                            new_cat    = ef2.selectbox("Category", _EXP_CATS, index=cat_idx)
                            new_amt    = ef1.number_input("Amount (₦)", value=safe_float(r["amount"]),
                                                          min_value=0.0, step=100.0)
                            new_date   = ef2.date_input(
                                "Date",
                                value=r["expense_date"].date() if pd.notna(r["expense_date"]) else datetime.now().date(),
                            )
                            save_exp   = st.form_submit_button("💾 Save Changes", type="primary")

                        if save_exp:
                            ok = db_update(TBL_EXPENSES, "expense_id", exp_id, {
                                "description": new_name.strip(),
                                "category":     new_cat,
                                "amount":       new_amt,
                                "expense_date": str(new_date),
                            })
                            st.session_state[f"exp_msg_{exp_id}"] = (
                                "✅ Expense updated." if ok else "❌ Failed to update."
                            )
                            st.rerun()

                        if f"exp_msg_{exp_id}" in st.session_state:
                            msg = st.session_state.pop(f"exp_msg_{exp_id}")
                            (st.success if msg.startswith("✅") else st.error)(msg)

                        confirm_key = f"confirm_del_exp_{exp_id}"
                        if not st.session_state.get(confirm_key, False):
                            if st.button("🗑️ Delete this expense", key=f"del_exp_{exp_id}"):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            st.warning("⚠️ Delete this expense permanently?")
                            ce1, ce2 = st.columns(2)
                            if ce1.button("✅ Yes, delete", key=f"yes_del_exp_{exp_id}", type="primary"):
                                ok = db_delete(TBL_EXPENSES, "expense_id", exp_id)
                                st.session_state.pop(confirm_key, None)
                                st.session_state["exp_del_msg"] = (
                                    "✅ Expense deleted." if ok else "❌ Failed to delete."
                                )
                                st.rerun()
                            if ce2.button("❌ Cancel", key=f"no_del_exp_{exp_id}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

                        if "exp_del_msg" in st.session_state:
                            msg = st.session_state.pop("exp_del_msg")
                            (st.success if msg.startswith("✅") else st.error)(msg)

                if exp_pages > 1:
                    st.markdown("---")
                    ep1, ep2, ep3 = st.columns([1, 3, 1])
                    if ep1.button("◀ Prev", disabled=(exp_pg <= 1), key="exp_prev"):
                        st.session_state.exp_page = max(1, exp_pg-1); st.rerun()
                    ep2.markdown(
                        f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>"
                        f"Page {exp_pg} of {exp_pages}</div>",
                        unsafe_allow_html=True,
                    )
                    if ep3.button("Next ▶", disabled=(exp_pg >= exp_pages), key="exp_next"):
                        st.session_state.exp_page = min(exp_pages, exp_pg+1); st.rerun()

    # ══════════════════════
    # Tab 2 — Log Expense
    # ══════════════════════
    with tab2:
        with st.form("log_expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            exp_name   = col1.text_input("Description *", placeholder="e.g. Generator fuel")
            category   = col2.selectbox("Category", [
                "Rent","Utilities","Salaries","Supplies","Transport",
                "Marketing","Maintenance","Taxes","Miscellaneous",
            ])
            amount       = col1.number_input("Amount (₦) *", min_value=0.0, step=100.0)
            expense_date = col2.date_input("Date", value=datetime.now().date())
            submitted    = st.form_submit_button("Log Expense", width='stretch', type="primary")

        if submitted:
            if not exp_name or amount <= 0:
                st.error("Please fill in description and a valid amount.")
            else:
                ok = db_insert(TBL_EXPENSES, {
                    "expense_id":   gen_id("EXP"),
                    "business_id":  business_id,
                    "description": exp_name.strip(),
                    "category":     category,
                    "amount":       amount,
                    "expense_date": str(expense_date),
                    "recorded_by":  user.get("full_name", user.get("email", "")),
                })
                if ok:
                    st.session_state["exp_log_msg"] = f"✅ Expense logged: {exp_name} — {fmt_naira(amount)}"
                    st.rerun()
                else:
                    st.error("Failed to log expense.")


# ══════════════════════════════════════════════════════════════════════════════
# INSIGHTS
# ══════════════════════════════════════════════════════════════════════════════

def page_insights():
    apply_suite_css()
    apply_theme_mode()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("🧠 Business Insights", "Data-driven intelligence for smarter decisions")

    with st.spinner("Crunching your numbers…"):
        sales_df    = get_sales_df(business_id)
        products_df = get_products_df(business_id)
        expenses_df = get_expenses_df(business_id)
        items_df    = db_fetch(TBL_SALE_ITEMS, {"business_id": business_id})
        insights    = compute_insights(sales_df, products_df, expenses_df, items_df)
        kpis        = compute_kpis(sales_df, expenses_df)

    if sales_df.empty:
        st.info("📭 No data yet. Record some sales to unlock insights.")
        return

    # ── Summary KPIs ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Avg Daily Revenue", fmt_naira(insights["avg_daily_revenue"]),
                 "Based on all recorded days", icon="📅")
    with c2:
        kpi_card("Best Sales Day", insights.get("best_day","N/A"),
                 "Highest revenue weekday", icon="🏆")
    with c3:
        kpi_card("Slowest Day", insights.get("worst_day","N/A"),
                 "Lowest revenue weekday", icon="🐢")
    with c4:
        best = (insights["top_products_revenue"].iloc[0]["product_name"]
                if not insights["top_products_revenue"].empty else "N/A")
        kpi_card("Best Seller", best, "By total revenue", icon="⭐")

    # ── Net Profit Banner ──
    net = kpis["net_profit"]
    banner_color = "#0a2a1e" if net >= 0 else "#2a0a11"
    border_color = "#00C896" if net >= 0 else "#FF4D6D"
    text_color   = "#00C896" if net >= 0 else "#FF4D6D"
    st.markdown(f"""
<div style="background:{banner_color};border:1px solid {border_color};
border-radius:12px;padding:1rem 1.25rem;margin:1rem 0;
display:flex;align-items:center;justify-content:space-between;">
  <div>
    <div style="font-size:0.7rem;color:#8BA0B8;text-transform:uppercase;
    letter-spacing:0.1em;font-family:'DM Mono',monospace;margin-bottom:0.25rem;">
      Net Profit This Month</div>
    <div style="font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;
    color:{text_color};letter-spacing:-0.04em;">{fmt_naira(net)}</div>
  </div>
  <div style="text-align:right;font-size:0.82rem;color:#8BA0B8;">
    Revenue: {fmt_naira(kpis['month_revenue'])}<br>
    Gross Profit: {fmt_naira(kpis['month_profit'])}<br>
    Expenses: {fmt_naira(kpis['month_expenses'])}
  </div>
</div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📈 Trends", "🏆 Products", "📦 Inventory", "📅 Weekday", "📊 Export"]
    )

    # ══════════════════════
    # Tab 1 — Monthly Trends
    # ══════════════════════
    with tab1:
        section_header("Monthly Performance Comparison")

        if not sales_df.empty:
            ms = sales_df.copy()
            ms["year"]        = ms["sale_date"].dt.year
            ms["month_label"] = ms["sale_date"].dt.strftime("%b %Y")
            ms["month_sort"]  = ms["sale_date"].dt.to_period("M")

            available_years = sorted(ms["year"].unique().tolist(), reverse=True)
            tf1, tf2, tf3   = st.columns(3)
            selected_year   = tf1.selectbox("Year", ["All years"] + [str(y) for y in available_years],
                                            key="ins_year")
            metric_choice   = tf2.selectbox("Metric",
                                            ["Revenue & Profit","Revenue only","Profit only",
                                             "All (Revenue, Cost, Profit)"],
                                            key="ins_metric")
            num_months      = tf3.slider("Last N months", min_value=3, max_value=24,
                                         value=12, key="ins_months")

            if selected_year != "All years":
                ms = ms[ms["year"] == int(selected_year)]

            monthly = (
                ms.groupby(["month_sort","month_label"])
                .agg(
                    revenue  =("total_amount","sum"),
                    cost     =("cost_total","sum"),
                    profit   =("gross_profit","sum"),
                    txn_count=("sale_id","count"),
                )
                .reset_index()
                .sort_values("month_sort")
            )

            if not expenses_df.empty:
                ex = expenses_df.copy()
                ex["month_sort"] = ex["expense_date"].dt.to_period("M")
                monthly_exp = (
                    ex.groupby("month_sort")["amount"].sum()
                    .reset_index().rename(columns={"amount":"expenses"})
                )
                monthly = monthly.merge(monthly_exp, on="month_sort", how="left")
                monthly["expenses"]   = monthly["expenses"].fillna(0)
                monthly["net_profit"] = monthly["profit"] - monthly["expenses"]
            else:
                monthly["expenses"]   = 0
                monthly["net_profit"] = monthly["profit"]

            monthly = monthly.tail(num_months)

            if monthly.empty:
                st.info("No data for the selected filters.")
            else:
                best_rev_row  = monthly.loc[monthly["revenue"].idxmax()]
                best_prof_row = monthly.loc[monthly["net_profit"].idxmax()]
                mom_growth    = 0
                if len(monthly) >= 2:
                    last_rev = monthly.iloc[-1]["revenue"]
                    prev_rev = monthly.iloc[-2]["revenue"]
                    if prev_rev:
                        mom_growth = (last_rev - prev_rev) / prev_rev * 100

                sk1, sk2, sk3, sk4 = st.columns(4)
                with sk1:
                    kpi_card("Best Month (Revenue)", best_rev_row["month_label"],
                             fmt_naira(best_rev_row["revenue"]), icon="🏆")
                with sk2:
                    kpi_card("Best Month (Profit)", best_prof_row["month_label"],
                             fmt_naira(best_prof_row["net_profit"]), icon="💎")
                with sk3:
                    kpi_card("Latest Month Growth",
                             f"{'▲' if mom_growth >= 0 else '▼'} {abs(mom_growth):.1f}%",
                             "vs previous month", positive=(mom_growth >= 0), icon="📈")
                with sk4:
                    kpi_card("Period Total", fmt_naira(monthly["revenue"].sum()),
                             f"{int(monthly['txn_count'].sum())} transactions", icon="📊")

                st.markdown("---")

                x_labels = monthly["month_label"].tolist()
                fig = go.Figure()
                if metric_choice in ["Revenue & Profit","Revenue only","All (Revenue, Cost, Profit)"]:
                    fig.add_trace(go.Bar(name="Revenue", x=x_labels, y=monthly["revenue"],
                                        marker_color="#6366f1",
                                        hovertemplate="%{x}<br>Revenue: ₦%{y:,.0f}<extra></extra>"))
                if metric_choice == "All (Revenue, Cost, Profit)":
                    fig.add_trace(go.Bar(name="Cost", x=x_labels, y=monthly["cost"],
                                        marker_color="#ef4444",
                                        hovertemplate="%{x}<br>Cost: ₦%{y:,.0f}<extra></extra>"))
                if metric_choice in ["Revenue & Profit","Profit only","All (Revenue, Cost, Profit)"]:
                    fig.add_trace(go.Bar(name="Net Profit", x=x_labels, y=monthly["net_profit"],
                                        marker_color="#00C896",
                                        hovertemplate="%{x}<br>Net Profit: ₦%{y:,.0f}<extra></extra>"))
                fig.update_layout(
                    barmode="group",
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=20, b=0), height=320,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="right", x=1, font=dict(size=11)),
                    xaxis=dict(type="category", tickangle=-45, tickfont=dict(size=10),
                               gridcolor="rgba(0,0,0,0)"),
                    yaxis=dict(tickprefix="₦", tickformat=",.0f",
                               gridcolor="rgba(255,255,255,0.06)", tickfont=dict(size=11)),
                    bargap=0.2, bargroupgap=0.05,
                )
                with st.expander("📈 Monthly Performance Chart", expanded=True):
                    st.plotly_chart(fig, width='stretch')

                with st.expander("📋 View monthly breakdown table"):
                    dm = monthly[["month_label","revenue","cost","profit",
                                  "expenses","net_profit","txn_count"]].copy()
                    dm.columns = ["Month","Revenue","Cost","Gross Profit",
                                  "Expenses","Net Profit","Transactions"]
                    for col in ["Revenue","Cost","Gross Profit","Expenses","Net Profit"]:
                        dm[col] = dm[col].apply(fmt_naira)
                    st.dataframe(dm, width='stretch', hide_index=True)

        # Category performance
        st.markdown("---")
        section_header("Category Performance")
        if not insights["category_revenue"].empty:
            with st.expander("🗂️ Revenue by Category", expanded=True):
                cat_fig = px.bar(
                    insights["category_revenue"].sort_values("total_amount"),
                    x="total_amount", y="category", orientation="h",
                    labels={"total_amount":"Revenue (₦)","category":""},
                    color_discrete_sequence=["#F5A623"],
                )
                cat_fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=max(200, len(insights["category_revenue"]) * 45),
                    xaxis=dict(tickprefix="₦", tickformat=",.0f",
                               gridcolor="rgba(255,255,255,0.06)"),
                )
                st.plotly_chart(cat_fig, width='stretch')
        else:
            st.info("No category data yet.")

    # ══════════════════════
    # Tab 2 — Products
    # ══════════════════════
    with tab2:
        with st.expander("🏆 Top Products by Revenue", expanded=True):
            col_l, col_r = st.columns(2)
            with col_l:
                section_header("By Revenue")
                if not insights["top_products_revenue"].empty:
                    fig = px.bar(
                        insights["top_products_revenue"].sort_values("total_amount"),
                        x="total_amount", y="product_name", orientation="h",
                        labels={"total_amount":"Revenue (₦)","product_name":""},
                        color_discrete_sequence=["#6366f1"],
                    )
                    fig.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=10, b=0), height=350,
                        xaxis=dict(tickprefix="₦"),
                    )
                    st.plotly_chart(fig, width='stretch')

            with col_r:
                section_header("By Quantity Sold")
                if not insights["top_products_qty"].empty:
                    fig2 = px.bar(
                        insights["top_products_qty"].sort_values("quantity"),
                        x="quantity", y="product_name", orientation="h",
                        labels={"quantity":"Units Sold","product_name":""},
                        color_discrete_sequence=["#10b981"],
                    )
                    fig2.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=10, b=0), height=350,
                    )
                    st.plotly_chart(fig2, width='stretch')

        section_header("⚠️ Slow-Moving Products (Last 30 Days)")
        if not insights["slow_movers"].empty:
            st.dataframe(
                insights["slow_movers"].rename(
                    columns={"product_name":"Product","quantity":"Units Sold (30d)"}
                ),
                width='stretch',
            )
        else:
            st.markdown('<div class="alert-success">✅ All products are selling at healthy rates.</div>',
                        unsafe_allow_html=True)

    # ══════════════════════
    # Tab 3 — Inventory
    # ══════════════════════
    with tab3:
        # ── Expiry Alerts ──────────────────────────────────────────────────────
        _expired       = insights.get("expired",       pd.DataFrame())
        _expiring_soon = insights.get("expiring_soon", pd.DataFrame())

        if not _expired.empty or not _expiring_soon.empty:
            section_header("🚨 Product Expiry Alerts")

            # Expired products
            if not _expired.empty:
                st.markdown(
                    '<div class="alert-critical">🔴 <strong>Expired Products</strong> — '
                    'Remove from shelves immediately and stop selling.</div>',
                    unsafe_allow_html=True,
                )
                for _, r in _expired.iterrows():
                    days_ago = abs(int(r["days_to_expiry"]))
                    exp_str  = pd.Timestamp(r["expiry_date"]).strftime("%d %b %Y")
                    st.markdown(
                        f'<div class="alert-critical" style="margin-top:6px;">❌ <strong>{r["product_name"]}</strong>'
                        f' — Expired <strong>{days_ago} day{"s" if days_ago != 1 else ""} ago</strong>'
                        f' ({exp_str}) | Stock: {safe_int(r["stock_quantity"])} units</div>',
                        unsafe_allow_html=True,
                    )

            # Expiring soon
            if not _expiring_soon.empty:
                st.markdown(
                    '<div class="alert-low" style="margin-top:10px;">🟡 <strong>Expiring Within 60 Days</strong> — '
                    'Prioritise sales or return to supplier.</div>',
                    unsafe_allow_html=True,
                )
                for _, r in _expiring_soon.iterrows():
                    days_left = int(r["days_to_expiry"])
                    exp_str   = pd.Timestamp(r["expiry_date"]).strftime("%d %b %Y")
                    urgency   = "alert-critical" if days_left <= 14 else "alert-low"
                    st.markdown(
                        f'<div class="{urgency}" style="margin-top:6px;">⚠️ <strong>{r["product_name"]}</strong>'
                        f' — Expires in <strong>{days_left} day{"s" if days_left != 1 else ""}</strong>'
                        f' ({exp_str}) | Stock: {safe_int(r["stock_quantity"])} units</div>',
                        unsafe_allow_html=True,
                    )
        else:
            section_header("🚨 Product Expiry Alerts")
            st.markdown(
                '<div class="alert-success">✅ No expiry alerts. All dated products are well within date.</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        section_header("🔴 Low Stock Products")
        if not insights["low_stock"].empty:
            for _, r in insights["low_stock"].iterrows():
                qty = safe_int(r["stock_quantity"])
                css = "alert-critical" if qty <= 0 else "alert-low"
                st.markdown(
                    f'<div class="{css}">⚠️ <strong>{r["product_name"]}</strong> '
                    f'— {qty} units left (reorder at {safe_int(r["reorder_level"])})</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="alert-success">✅ All products have sufficient stock.</div>',
                        unsafe_allow_html=True)

        section_header("📅 Projected Stockout Dates")
        if not insights["stockout_projection"].empty:
            proj = insights["stockout_projection"].copy()
            proj["stockout_date"] = proj["days_until_stockout"].apply(
                lambda d: (datetime.now() + timedelta(days=d)).strftime("%d %b %Y")
            )
            proj["urgency"] = proj["days_until_stockout"].apply(
                lambda d: "🔴 Critical" if d <= 3 else ("🟡 Soon" if d <= 7 else "🟢 OK")
            )
            st.dataframe(
                proj[["product_name","stock_quantity","avg_daily_sales",
                      "days_until_stockout","stockout_date","urgency"]]
                .rename(columns={
                    "product_name":       "Product",
                    "stock_quantity":     "Current Stock",
                    "avg_daily_sales":    "Avg Daily Sales",
                    "days_until_stockout":"Days Left",
                    "stockout_date":      "Est. Stockout Date",
                    "urgency":            "Status",
                }),
                width='stretch',
            )
        else:
            st.info("Not enough sales history to project stockout dates.")

    # ══════════════════════
    # Tab 4 — Weekday
    # ══════════════════════
    with tab4:
        section_header("Revenue by Day of Week")
        if not insights["weekday_performance"].empty:
            with st.expander("📅 Weekday Revenue Chart", expanded=True):
                wd     = insights["weekday_performance"]
                colors = [
                    "#ef4444" if r == wd["revenue"].min()
                    else ("#10b981" if r == wd["revenue"].max() else "#6366f1")
                    for r in wd["revenue"]
                ]
                fig = go.Figure(go.Bar(
                    x=wd["weekday"], y=wd["revenue"],
                    marker_color=colors,
                    text=[fmt_naira(v) for v in wd["revenue"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    yaxis=dict(tickprefix="₦", gridcolor="rgba(255,255,255,0.06)"),
                    height=350,
                )
                st.plotly_chart(fig, width='stretch')

            if insights["best_day"] and insights["worst_day"]:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        f'<div class="alert-success">🏆 <strong>Best day:</strong> '
                        f'{insights["best_day"]} — schedule more staff and stock up.</div>',
                        unsafe_allow_html=True,
                    )
                with col2:
                    st.markdown(
                        f'<div class="alert-low">💡 <strong>Slowest day:</strong> '
                        f'{insights["worst_day"]} — consider promotions or discounts.</div>',
                        unsafe_allow_html=True,
                    )

    # ══════════════════════
    # Tab 5 — Export
    # ══════════════════════
    with tab5:
        section_header("📥 Download Your Data")
        col1, col2, col3 = st.columns(3)
        with col1:
            if not sales_df.empty:
                st.download_button("⬇️ Download Sales CSV",
                                   data=sales_df.to_csv(index=False).encode("utf-8"),
                                   file_name="sales_export.csv", mime="text/csv",
                                   width='stretch')
        with col2:
            products_df = get_products_df(business_id)
            if not products_df.empty:
                st.download_button("⬇️ Download Products CSV",
                                   data=products_df.to_csv(index=False).encode("utf-8"),
                                   file_name="products_export.csv", mime="text/csv",
                                   width='stretch')
        with col3:
            if not expenses_df.empty:
                st.download_button("⬇️ Download Expenses CSV",
                                   data=expenses_df.to_csv(index=False).encode("utf-8"),
                                   file_name="expenses_export.csv", mime="text/csv",
                                   width='stretch')



# ══════════════════════════════════════════════════════════════════════════════
# DEBTORS LEDGER — CUSTOMER STATEMENT
# ══════════════════════════════════════════════════════════════════════════════

def page_debtor_statement(customer_name: str):
    """
    Full statement of account for a single customer — all their debts and
    payments merged into one chronological timeline with running balance.
    """
    apply_suite_css()
    apply_theme_mode()
    import urllib.parse

    user        = st.session_state.user
    business_id = user["business_id"]

    if st.button("← Back to Debtors Ledger", key="back_to_ledger"):
        st.session_state.pop("debtor_statement_customer", None)
        st.rerun()

    debts_df = get_debts_df(business_id)
    all_items_df = get_sale_items_df(business_id)
    debt_pays_df = get_debt_payments_df(business_id)

    cust_debts = debts_df[
        debts_df["customer_name"].str.strip().str.lower() == customer_name.strip().lower()
    ].copy() if not debts_df.empty else pd.DataFrame()

    if cust_debts.empty:
        st.warning(f"No debt records found for **{customer_name}**.")
        return

    cphone = cust_debts.iloc[0].get("customer_phone", "") or ""
    first_date = cust_debts["sale_date"].min()
    since_str  = first_date.strftime("%b %Y") if pd.notna(first_date) else "—"

    total_purchased = cust_debts["total_amount"].sum()
    total_paid      = cust_debts["amount_paid"].sum()
    still_owing     = cust_debts["balance"].sum()

    initials = "".join(p[0].upper() for p in customer_name.split()[:2])

    # ── Header ──
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;
                padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:16px;">
      <div style="width:52px;height:52px;border-radius:50%;
                  background:var(--gold-glow);border:1.5px solid var(--gold-dim);
                  display:flex;align-items:center;justify-content:center;
                  font-size:18px;font-weight:500;color:var(--gold);flex-shrink:0;">
        {initials}
      </div>
      <div>
        <div style="font-size:22px;font-weight:600;color:var(--text-primary);
                    letter-spacing:-0.03em;">{customer_name}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:3px;">
          {"📞 " + cphone + "  ·  " if cphone else ""}Customer since {since_str}
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Summary KPIs ──
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Total Purchased", fmt_naira(total_purchased), "across all sales")
    with c2:
        kpi_card("Total Paid", fmt_naira(total_paid), "all instalments", positive=True)
    with c3:
        kpi_card("Still Owing", fmt_naira(still_owing),
                 "current balance", positive=(still_owing <= 0))

    st.markdown("---")

    # ── WhatsApp reminder ──
    if cphone and still_owing > 0:
        reminder_text = (
            f"Hello {customer_name}, this is a reminder from "
            f"{user.get('business_name', 'our business')}.\n"
            f"You have an outstanding balance of {fmt_naira(still_owing)}.\n"
            f"Kindly make payment at your earliest convenience.\n\n"
            f"Thank you 🙏\nPowered by BizTrack-OS"
        )
        wa_url = (
            f"https://wa.me/{cphone.replace('+','').replace(' ','')}?"
            f"text={urllib.parse.quote(reminder_text)}"
        )
        st.markdown(
            f'''<a href="{wa_url}" target="_blank"
                style="display:block;text-align:center;
                       background:#25D366;color:white;
                       padding:0.5rem;border-radius:8px;
                       font-weight:600;text-decoration:none;
                       margin-bottom:1rem;">
                💬 Send WhatsApp Reminder · {fmt_naira(still_owing)} outstanding
            </a>''',
            unsafe_allow_html=True,
        )

    # ── Build unified timeline ──
    # Each event: type (sale|payment), date, debt_id, description, amount, running_balance
    events = []

    for _, debt in cust_debts.sort_values("sale_date").iterrows():
        debt_id   = debt["debt_id"]
        sale_date = debt["sale_date"]
        total     = safe_float(debt["total_amount"])
        paid_now  = safe_float(debt.get("amount_paid", 0))
        status    = debt.get("status", "unpaid")

        # Build item description
        sid = debt.get("sale_id")
        desc = "Credit sale"
        if sid and not all_items_df.empty:
            items = all_items_df[all_items_df["sale_id"] == sid]
            if not items.empty:
                parts = [
                    f"{r['product_name']} ×{int(r['quantity'])}"
                    for _, r in items.head(3).iterrows()
                ]
                if len(items) > 3:
                    parts.append(f"+{len(items)-3} more")
                desc = ", ".join(parts)

        events.append({
            "type":    "sale",
            "date":    sale_date,
            "debt_id": debt_id,
            "sale_id": sid,
            "desc":    desc,
            "amount":  total,
            "paid_at_sale": paid_now if status != "settled" or not debt_pays_df.empty else paid_now,
            "status":  status,
        })

    if not debt_pays_df.empty:
        cust_debt_ids = set(cust_debts["debt_id"].tolist())
        cust_pays = debt_pays_df[debt_pays_df["debt_id"].isin(cust_debt_ids)].copy()
        for _, pay in cust_pays.iterrows():
            events.append({
                "type":    "payment",
                "date":    pay["payment_date"],
                "debt_id": pay["debt_id"],
                "desc":    pay.get("note") or "Payment received",
                "amount":  safe_float(pay["amount"]),
            })

    events.sort(key=lambda e: e["date"] if pd.notna(e["date"]) else pd.Timestamp.min)

    # Compute running balance
    running = 0.0
    for e in events:
        if e["type"] == "sale":
            running += e["amount"]
            # Subtract any upfront partial payment recorded on the sale row itself
            # (only count it here if there are no separate payment rows for this debt)
            debt_id = e["debt_id"]
            has_pay_rows = (
                not debt_pays_df.empty
                and debt_id in debt_pays_df["debt_id"].values
            )
            if not has_pay_rows:
                running -= e.get("paid_at_sale", 0)
        else:
            running -= e["amount"]
        e["running_balance"] = round(running, 2)

    # ── Render timeline ──
    section_header("Full Transaction History")

    for e in reversed(events):   # newest first
        etype   = e["type"]
        date_s  = e["date"].strftime("%d %b %Y") if pd.notna(e["date"]) else "—"
        rb      = e["running_balance"]
        rb_col  = "#D63355" if rb > 0 else "var(--jade)"
        rb_bg   = "rgba(255,77,109,0.08)" if rb > 0 else "rgba(0,200,150,0.08)"
        rb_bdr  = "rgba(255,77,109,0.25)" if rb > 0 else "rgba(0,200,150,0.25)"

        if etype == "sale":
            dot_col  = "var(--gold)"
            type_lbl = "Credit Sale"
            type_col = "var(--gold)"
            settled_badge = (
                ' <span style="background:var(--surface2);border:0.5px solid var(--border2);'
                'border-radius:20px;padding:2px 8px;font-size:10px;'
                'color:var(--text-muted);margin-left:6px;">Settled</span>'
                if e.get("status") == "settled" else ""
            )
            amount_html = f"""
              <div style="display:flex;gap:16px;margin-top:8px;padding-top:8px;
                          border-top:0.5px solid var(--border);">
                <div><div style="font-size:10px;color:var(--text-muted);">Billed</div>
                     <div style="font-weight:500;color:var(--text-primary);">{fmt_naira(e['amount'])}</div></div>
              </div>
            """
        else:
            dot_col  = "var(--jade)"
            type_lbl = "Payment"
            type_col = "var(--jade)"
            settled_badge = ""
            amount_html = f"""
              <div style="display:flex;gap:16px;margin-top:8px;padding-top:8px;
                          border-top:0.5px solid var(--border);">
                <div><div style="font-size:10px;color:var(--text-muted);">Amount paid</div>
                     <div style="font-weight:500;color:var(--jade);">{fmt_naira(e['amount'])}</div></div>
              </div>
            """

        st.markdown(f"""
        <div style="display:flex;gap:14px;margin-bottom:10px;">
          <div style="display:flex;flex-direction:column;align-items:center;width:18px;flex-shrink:0;">
            <div style="width:10px;height:10px;border-radius:50%;
                        background:{dot_col};margin-top:14px;flex-shrink:0;"></div>
            <div style="width:1.5px;flex:1;background:var(--border);margin:3px 0;min-height:20px;"></div>
          </div>
          <div style="flex:1;background:var(--surface);border:0.5px solid var(--border);
                      border-radius:10px;padding:10px 14px;margin-bottom:2px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-size:11px;font-weight:500;text-transform:uppercase;
                           letter-spacing:0.07em;color:{type_col};">{type_lbl}{settled_badge}</span>
              <span style="font-size:11px;color:var(--text-muted);">{date_s}</span>
            </div>
            <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">{e['desc']}</div>
            {amount_html}
            <div style="text-align:right;margin-top:6px;">
              <span style="font-size:11px;font-weight:500;padding:2px 10px;border-radius:20px;
                           background:{rb_bg};border:0.5px solid {rb_bdr};color:{rb_col};">
                Balance: {fmt_naira(rb)}
              </span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Record payment form at the bottom ──
    open_debts = cust_debts[cust_debts["status"] != "settled"]
    if not open_debts.empty:
        st.markdown("---")
        section_header("Record a Payment")

        debt_options = {
            f"{fmt_naira(safe_float(r['balance']))} owing — sale {r.get('sale_id','')[:8]}… ({r['sale_date'].strftime('%d %b %Y') if pd.notna(r['sale_date']) else '—'})": r["debt_id"]
            for _, r in open_debts.sort_values("sale_date").iterrows()
        }

        with st.form("stmt_pay_form"):
            selected_label = st.selectbox(
                "Apply payment to which sale?",
                options=list(debt_options.keys()),
            )
            selected_debt_id = debt_options[selected_label]
            selected_balance = safe_float(
                open_debts[open_debts["debt_id"] == selected_debt_id].iloc[0]["balance"]
            )

            pf1, pf2 = st.columns(2)
            pay_amount = pf1.number_input(
                "Amount Received (₦)",
                min_value=100.0,
                max_value=float(selected_balance),
                value=float(selected_balance),
                step=100.0,
            )
            pay_note = pf2.text_input("Note (optional)", placeholder="e.g. Cash at shop")

            pay_btn = st.form_submit_button(
                f"💰 Record Payment — {fmt_naira(pay_amount)}",
                type="primary", width="stretch",
            )

        if pay_btn:
            ok = record_debt_payment(selected_debt_id, business_id, pay_amount, pay_note)
            if ok:
                remaining = round(selected_balance - pay_amount, 2)
                if remaining <= 0:
                    st.success(f"✅ Debt fully settled for {customer_name}!")
                else:
                    st.success(
                        f"✅ Payment of {fmt_naira(pay_amount)} recorded. "
                        f"Remaining balance: {fmt_naira(remaining)}"
                    )
                st.rerun()


# DEBTORS LEDGER
# ══════════════════════════════════════════════════════════════════════════════

def page_debtors():
    """
    Debtors Ledger — tracks part payments and credit sales.
    Lets the business owner:
      • View all outstanding debts sorted by oldest first
      • Click a customer name to open their full statement
      • Record instalment payments against any open debt
      • Send a WhatsApp reminder to the debtor in one tap
      • See full payment history per debt
      • Mark debts as settled
    """
    apply_suite_css()
    apply_theme_mode()

    # ── Route to customer statement if one is selected ──
    if st.session_state.get("debtor_statement_customer"):
        page_debtor_statement(st.session_state["debtor_statement_customer"])
        return

    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📕 Debtors Ledger", "Track credit sales and part payments")

    import urllib.parse
    from datetime import timedelta

    debts_df = get_debts_df(business_id)

    # Load all sale items once — filtered per-debt inside the loop (no N+1 queries)
    all_items_df = get_sale_items_df(business_id)

    # ── Summary KPIs ──
    if not debts_df.empty:
        active_df   = debts_df[debts_df["status"] != "settled"]
        settled_df  = debts_df[debts_df["status"] == "settled"]
        total_owed  = active_df["balance"].sum()
        total_debtors = active_df["customer_name"].nunique()
        oldest_days = 0
        if not active_df.empty and "sale_date" in active_df.columns:
            valid_dates = active_df["sale_date"].dropna()
            if not valid_dates.empty:
                oldest_days = (datetime.now() - valid_dates.min()).days

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Total Outstanding", fmt_naira(total_owed),
                     f"{len(active_df)} open debts", positive=False, icon="📕")
        with c2:
            kpi_card("Active Debtors", str(total_debtors),
                     "Unique customers owing", icon="👥")
        with c3:
            kpi_card("Oldest Debt", f"{oldest_days} days",
                     "Days since oldest unpaid sale", positive=(oldest_days <= 7), icon="⏳")
        with c4:
            kpi_card("Settled Debts", str(len(settled_df)),
                     fmt_naira(settled_df["total_amount"].sum() if not settled_df.empty else 0),
                     positive=True, icon="✅")
    else:
        st.info("📭 No credit sales recorded yet. When you record a Part Payment or Credit sale, it will appear here.")
        return

    st.markdown("---")

    # ── Quick jump to customer statement ──
    all_customers = sorted(debts_df["customer_name"].dropna().unique().tolist())
    if all_customers:
        with st.expander("🔍 Jump to Customer Statement", expanded=False):
            selected = st.selectbox(
                "Select a customer",
                options=all_customers,
                key="quick_jump_customer",
            )
            if st.button("📋 Open Statement", key="quick_jump_btn", type="primary"):
                st.session_state["debtor_statement_customer"] = selected
                st.rerun()

    st.markdown("---")

    # ── Filter tabs ──
    tab_open, tab_settled, tab_all = st.tabs(["🔴 Outstanding", "✅ Settled", "📋 All Debts"])

    for tab, status_filter, label in [
        (tab_open,    ["partial", "unpaid"], "outstanding"),
        (tab_settled, ["settled"],           "settled"),
        (tab_all,     None,                  "all"),
    ]:
        with tab:
            if status_filter:
                view_df = debts_df[debts_df["status"].isin(status_filter)].copy()
            else:
                view_df = debts_df.copy()

            if view_df.empty:
                st.info(f"No {label} debts.")
                continue

            # Sort oldest first for outstanding, newest first for settled
            if status_filter != ["settled"]:
                view_df = view_df.sort_values("sale_date", ascending=True)
            else:
                view_df = view_df.sort_values("sale_date", ascending=False)

            # Search filter
            search = st.text_input("🔍 Search by customer name",
                                   key=f"debt_search_{label}",
                                   placeholder="Customer name…")
            if search:
                view_df = view_df[
                    view_df["customer_name"].str.contains(search, case=False, na=False)
                ]

            st.caption(f"{len(view_df)} record(s)")
            st.markdown("---")

            for _, debt in view_df.iterrows():
                debt_id   = debt["debt_id"]
                cname     = debt.get("customer_name", "Unknown") or "Unknown"
                cphone    = debt.get("customer_phone", "") or ""
                balance   = safe_float(debt["balance"])
                paid      = safe_float(debt["amount_paid"])
                total     = safe_float(debt["total_amount"])
                status    = debt.get("status", "unpaid")
                sale_date = debt["sale_date"]
                days_old  = (datetime.now() - sale_date).days if pd.notna(sale_date) else 0

                # Urgency colour
                if status == "settled":
                    urgency_css = "alert-success"
                    urgency_icon = "✅"
                elif days_old > 14:
                    urgency_css = "alert-critical"
                    urgency_icon = "🔴"
                elif days_old > 7:
                    urgency_css = "alert-low"
                    urgency_icon = "🟡"
                else:
                    urgency_css = ""
                    urgency_icon = "🟢"

                date_str = sale_date.strftime("%d %b %Y") if pd.notna(sale_date) else "—"
                expander_label = (
                    f"{urgency_icon} **{cname}** | "
                    f"Owes: {fmt_naira(balance)} | "
                    f"Paid: {fmt_naira(paid)} / {fmt_naira(total)} | "
                    f"{date_str} ({days_old}d ago)"
                )

                with st.expander(expander_label, expanded=False):
                    # ── View full customer statement ──
                    if st.button(
                        f"📋 View Full Statement for {cname}",
                        key=f"stmt_btn_{debt_id}_{label}",
                        type="primary",
                    ):
                        st.session_state["debtor_statement_customer"] = cname
                        st.rerun()

                    st.markdown("---")
                    dc1.markdown(f"**Debt ID:** `{debt_id}`")
                    dc1.markdown(f"**Sale ID:** `{debt.get('sale_id', '—')}`")
                    dc1.markdown(f"**Customer:** {cname}")
                    dc1.markdown(f"**Phone:** {cphone if cphone else '—'}")
                    dc2.markdown(f"**Total Sale:** {fmt_naira(total)}")
                    dc2.markdown(f"**Amount Paid:** {fmt_naira(paid)}")
                    dc2.markdown(f"**Balance Owed:** `{fmt_naira(balance)}`")
                    dc2.markdown(f"**Status:** `{status.upper()}`")
                    if debt.get("note"):
                        st.caption(f"Note: {debt['note']}")

                    # ── Items in this sale ───────────────────────────
                    _sid = debt.get("sale_id")
                    if _sid and not all_items_df.empty:
                        _row_items = all_items_df[all_items_df["sale_id"] == _sid]
                        if not _row_items.empty:
                            with st.expander("🧾 Items in this sale", expanded=False):
                                for _, it in _row_items.iterrows():
                                    disc_note = (
                                        f"  *(disc: {fmt_naira(it['discount_amt'])})*"
                                        if it.get("discount_amt") else ""
                                    )
                                    st.markdown(
                                        f"• **{it['product_name']}** × {it['quantity']}  "
                                        f"@ {fmt_naira(it['unit_price'])}  → **{fmt_naira(it['line_total'])}**"
                                        + disc_note
                                    )
                                st.caption(
                                    f"Sale total: {fmt_naira(_row_items['line_total'].sum())}"
                                )

                    # ── Payment history ──
                    debt_pays = get_debt_payments_df(business_id)
                    if not debt_pays.empty:
                        this_debt_pays = debt_pays[debt_pays["debt_id"] == debt_id]
                        if not this_debt_pays.empty:
                            with st.expander("📋 Payment History", expanded=False):
                                for _, p in this_debt_pays.sort_values(
                                        "payment_date", ascending=False).iterrows():
                                    pdate = p["payment_date"].strftime("%d %b %Y %H:%M")                                             if pd.notna(p["payment_date"]) else "—"
                                    st.markdown(
                                        f"• {fmt_naira(p['amount'])} — {pdate}"
                                        + (f" — *{p['note']}*" if p.get("note") else "")
                                    )

                    st.markdown("---")

                    # ── Record instalment (only for open debts) ──
                    if status != "settled":
                        with st.form(f"pay_debt_{debt_id}_{label}"):
                            pf1, pf2 = st.columns(2)
                            pay_amount = pf1.number_input(
                                "Amount Received (₦)",
                                min_value=100.0,
                                max_value=float(balance),
                                value=float(balance),
                                step=100.0,
                                key=f"pay_amt_{debt_id}_{label}",
                            )
                            pay_note = pf2.text_input(
                                "Note (optional)",
                                placeholder="e.g. Cash at shop",
                                key=f"pay_note_{debt_id}_{label}",
                            )
                            pay_btn = st.form_submit_button(
                                f"💰 Record Payment — {fmt_naira(pay_amount)}",
                                type="primary", width="stretch",
                            )

                        if pay_btn:
                            ok = record_debt_payment(debt_id, business_id,
                                                     pay_amount, pay_note)
                            if ok:
                                remaining = round(balance - pay_amount, 2)
                                if remaining <= 0:
                                    st.success(f"✅ Debt fully settled for {cname}!")
                                else:
                                    st.success(
                                        f"✅ Payment of {fmt_naira(pay_amount)} recorded. "
                                        f"Remaining balance: {fmt_naira(remaining)}"
                                    )
                                st.rerun()

                        # ── WhatsApp reminder ──
                        if cphone:
                            reminder_text = (
                                f"Hello {cname}, this is a reminder from "
                                f"{user.get('business_name', 'our business')}.\n"
                                f"You have an outstanding balance of {fmt_naira(balance)}.\n"
                                f"Kindly make payment at your earliest convenience.\n\n"
                                f"Thank you \U0001f64f\n"
                                f"Powered by BizTrack-OS"
                            )
                            wa_url = (
                                f"https://wa.me/{cphone.replace('+','').replace(' ','')}?"
                                f"text={urllib.parse.quote(reminder_text)}"
                            )
                            st.markdown(
                                f'''<a href="{wa_url}" target="_blank"
                                    style="display:block;text-align:center;
                                           background:#25D366;color:white;
                                           padding:0.5rem;border-radius:8px;
                                           font-weight:600;text-decoration:none;
                                           margin-top:0.25rem;">
                                    💬 Send WhatsApp Reminder to {cname}
                                </a>''',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.caption("💡 Add customer phone number when recording the sale to enable WhatsApp reminders.")

                    # ── Manual settle button (for edge cases) ──
                    if status != "settled":
                        settle_key = f"settle_{debt_id}"
                        if not st.session_state.get(settle_key, False):
                            if st.button("🏳️ Mark as Settled (manually)",
                                         key=f"settle_btn_{debt_id}_{label}",
                                         help="Use only if paid outside the app"):
                                st.session_state[settle_key] = True
                                st.rerun()
                        else:
                            st.warning("Mark this debt as fully settled?")
                            sc1, sc2 = st.columns(2)
                            if sc1.button("✅ Yes, settle", key=f"yes_settle_{debt_id}_{label}",
                                          type="primary"):
                                db_update(TBL_DEBTS, "debt_id", debt_id, {
                                    "status":      "settled",
                                    "amount_paid": total,
                                    "balance":     0,
                                })
                                st.session_state.pop(settle_key, None)
                                st.success("✅ Debt marked as settled.")
                                st.rerun()
                            if sc2.button("❌ Cancel", key=f"no_settle_{debt_id}_{label}"):
                                st.session_state.pop(settle_key, None)
                                st.rerun()

                st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

def page_admin():
    apply_suite_css()
    apply_theme_mode()
    user = st.session_state.user
    if user.get("role") != "admin":
        st.error("⛔ Access denied.")
        return

    page_header("🛡️ Admin Panel", "BizTrack platform management")

    users_df = db_fetch(TBL_USERS)
    if users_df.empty:
        st.info("No users found.")
        return

    # ── Bulk expiry sweep ──────────────────────────────────────────────────────
    # Flip any "active" user whose subscription_end has passed to "expired".
    # This catches users whose trial/plan ended but who never logged back in
    # (since check_access() only runs on the user's own session).
    _now = datetime.now()
    _swept = False
    for _, _u in users_df.iterrows():
        if _u.get("plan_status") == "active":
            try:
                _end = datetime.strptime(str(_u["subscription_end"])[:10], "%Y-%m-%d")
                if _end < _now:
                    db_update(TBL_USERS, "user_id", _u["user_id"], {"plan_status": "expired"})
                    _swept = True
            except Exception:
                pass
    if _swept:
        users_df = db_fetch(TBL_USERS)  # reload only if something changed
    # ──────────────────────────────────────────────────────────────────────────

    # Platform stats
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Businesses", str(len(users_df)), "Registered accounts", icon="🏢")
    with c2:
        active = len(users_df[users_df["plan_status"] == "active"])
        kpi_card("Active Subscriptions", str(active), "Paying or trial users", icon="✅")
    with c3:
        pending = len(users_df[users_df["plan_status"] == "pending_payment"])
        kpi_card("Pending Payment", str(pending), "Awaiting manual activation", icon="⏳")
    with c4:
        monthly_rev = (len(users_df[(users_df["plan_type"] == "monthly") &
                                    (users_df["plan_status"] == "active")]) *
                       PAYMENT_DETAILS["monthly_price"])
        yearly_rev  = (len(users_df[(users_df["plan_type"] == "yearly") &
                                    (users_df["plan_status"] == "active")]) *
                       (PAYMENT_DETAILS["yearly_price"] / 12))
        kpi_card("Est. MRR", fmt_naira(monthly_rev + yearly_rev),
                 "From active paid plans", icon="📈")

    # Revenue ledger KPIs
    payments_df = get_payments_df()
    if not payments_df.empty:
        now_dt      = datetime.now()
        month_start = datetime(now_dt.year, now_dt.month, 1)
        year_start  = datetime(now_dt.year, 1, 1)

        total_collected = payments_df["amount"].sum()
        month_collected = payments_df[payments_df["payment_date"] >= month_start]["amount"].sum()
        year_collected  = payments_df[payments_df["payment_date"] >= year_start]["amount"].sum()
        total_txns      = len(payments_df)

        st.markdown("---")
        st.markdown("#### 💰 Platform Revenue — Actual Collected")
        r1, r2, r3, r4 = st.columns(4)
        with r1: kpi_card("All-Time Revenue",  fmt_naira(total_collected), f"{total_txns} payments", icon="💰")
        with r2: kpi_card("This Month",        fmt_naira(month_collected), now_dt.strftime("%B %Y"), icon="📅")
        with r3: kpi_card("This Year",         fmt_naira(year_collected),  str(now_dt.year),         icon="🗓️")
        with r4:
            avg = total_collected / total_txns if total_txns else 0
            kpi_card("Avg. per Payment", fmt_naira(avg), "Across all activations", icon="🧾")
    else:
        st.info("💡 No payment records yet.")

    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "⏳ Pending Activation", "✅ Active Users", "📈 MRR & Growth",
        "🚨 Churn Alerts", "🔑 Password Resets", "👥 All Users", "⛔ Deactivated",
        "👁️ User Activity",
    ])

    # ── Pending ──
    with tab1:
        pending_df = users_df[users_df["plan_status"] == "pending_payment"]
        if pending_df.empty:
            st.success("No pending activations.")
        else:
            for _, u in pending_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3,2,2])
                    with col1:
                        st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                        st.caption(f"📧 {u['email']} | 📱 {u.get('phone','—')} | Plan: {u['plan_type']} | Signed up: {u['created_at']}")
                    with col2:
                        plan   = u["plan_type"]
                        days   = 30 if plan == "monthly" else 365
                        end_dt = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                        if st.button("✅ Activate", key=f"act_{u['user_id']}"):
                            ok = db_update(TBL_USERS, "user_id", u["user_id"], {
                                "plan_status":        "active",
                                "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                                "subscription_end":   end_dt,
                            })
                            if ok:
                                pay_amount = (PAYMENT_DETAILS["yearly_price"]
                                              if plan == "yearly"
                                              else PAYMENT_DETAILS["monthly_price"])
                                log_payment(u["user_id"], u["business_name"],
                                            u["email"], plan, pay_amount, "Initial activation")
                                st.success(f"✅ {u['business_name']} activated until {end_dt}")
                                st.rerun()
                    with col3:
                        cdk = f"confirm_del_user_{u['user_id']}"
                        if not st.session_state.get(cdk, False):
                            if st.button("🗑️ Delete", key=f"del_u_{u['user_id']}"):
                                st.session_state[cdk] = True; st.rerun()
                        else:
                            st.warning("Delete this user?")
                            if st.button("✅ Confirm", key=f"yes_del_u_{u['user_id']}", type="primary"):
                                db_delete(TBL_USERS, "user_id", u["user_id"])
                                st.session_state.pop(cdk, None); st.rerun()
                            if st.button("❌ Cancel", key=f"no_del_u_{u['user_id']}"):
                                st.session_state.pop(cdk, None); st.rerun()
                    st.markdown("---")

    # ── Active ──
    with tab2:
        active_df = users_df[users_df["plan_status"] == "active"]
        if active_df.empty:
            st.info("No active users.")
        else:
            for _, u in active_df.iterrows():
                col1, col2, col3 = st.columns([3,2,2])
                with col1:
                    st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                    st.caption(f"📧 {u['email']} | 📱 {u.get('phone','—')} | {u['plan_type']} | Expires: {u.get('subscription_end','?')}")
                with col2:
                    new_plan = st.selectbox(
                        "Plan", ["monthly", "yearly"],
                        index=0 if u.get("plan_type","monthly") == "monthly" else 1,
                        key=f"plan_sel_{u['user_id']}",
                        label_visibility="collapsed"
                    )
                    ext_days   = 365 if new_plan == "yearly" else 30
                    ext_label  = "1 year" if ext_days == 365 else "30 days"
                    pay_amount = (PAYMENT_DETAILS["yearly_price"] if new_plan == "yearly"
                                  else PAYMENT_DETAILS["monthly_price"])
                    if st.button(f"🔁 Renew ({ext_label})", key=f"ext_{u['user_id']}"):
                        curr_end = parse_date(u.get("subscription_end",""))
                        base     = curr_end if (curr_end and curr_end > datetime.now()) else datetime.now()
                        new_end  = (base + timedelta(days=ext_days)).strftime("%Y-%m-%d")
                        db_update(TBL_USERS, "user_id", u["user_id"], {
                            "subscription_end": new_end,
                            "plan_type":        new_plan,
                        })
                        log_payment(u["user_id"], u["business_name"], u["email"],
                                    new_plan, pay_amount, "Renewal")
                        st.success(f"✅ Renewed ({new_plan}) to {new_end}"); st.rerun()
                with col3:
                    if st.button("⛔ Deactivate", key=f"deact_{u['user_id']}"):
                        db_update(TBL_USERS, "user_id", u["user_id"], {"plan_status": "expired"})
                        st.rerun()
                st.markdown("---")

    # ── MRR & Growth ──
    with tab3:
        if not payments_df.empty:
            section_header("Monthly Revenue Growth")
            with st.expander("💰 Platform MRR Chart", expanded=True):
                payments_df["month"] = payments_df["payment_date"].dt.to_period("M")
                mrr = (payments_df.groupby("month")["amount"].sum()
                       .reset_index()
                       .sort_values("month"))
                mrr["month_label"] = mrr["month"].astype(str)
                fig = go.Figure(go.Bar(
                    x=mrr["month_label"], y=mrr["amount"],
                    marker_color="#F5A623",
                    hovertemplate="%{x}<br>₦%{y:,.0f}<extra></extra>",
                ))
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=20, b=0),
                    yaxis=dict(tickprefix="₦", gridcolor="rgba(255,255,255,0.06)"),
                    xaxis=dict(type="category", tickangle=-45),
                    height=300,
                )
                st.plotly_chart(fig, width='stretch')
        else:
            st.info("No payment data yet.")

    # ── Churn Alerts ──
    with tab4:
        section_header("🚨 Subscriptions Expiring Soon (Next 7 Days)")
        active_df = users_df[users_df["plan_status"] == "active"].copy()
        if not active_df.empty:
            soon = []
            for _, u in active_df.iterrows():
                end = parse_date(u.get("subscription_end",""))
                if end:
                    days_left = (end - datetime.now()).days
                    if 0 <= days_left <= 7:
                        soon.append({**u.to_dict(), "days_left": days_left})
            if soon:
                for s in sorted(soon, key=lambda x: x["days_left"]):
                    css = "alert-critical" if s["days_left"] <= 2 else "alert-low"
                    st.markdown(
                        f'<div class="{css}">⚠️ <strong>{s["business_name"]}</strong> '
                        f'({s["email"]}) — expires in <strong>{s["days_left"]} day(s)</strong></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown('<div class="alert-success">✅ No subscriptions expiring in the next 7 days.</div>',
                            unsafe_allow_html=True)
        else:
            st.info("No active users.")

    # ── Password Resets ──
    with tab5:
        section_header("🔑 Pending Password Reset Requests")
        if not users_df.empty:
            reset_df = users_df[users_df.get("password_reset_requested","no") == "yes"] \
                       if "password_reset_requested" in users_df.columns else pd.DataFrame()
            if reset_df.empty:
                st.success("No pending password reset requests.")
            else:
                for _, u in reset_df.iterrows():
                    col1, col2 = st.columns([3,2])
                    with col1:
                        st.markdown(f"**{u['business_name']}** — {u['email']}")
                        st.caption(f"Requested: {u.get('reset_requested_at','?')}")
                    with col2:
                        new_pw_key = f"new_pw_{u['user_id']}"
                        new_pw = st.text_input("New temporary password",
                                               key=new_pw_key, type="password")
                        if st.button("✅ Reset", key=f"do_reset_{u['user_id']}"):
                            if new_pw and len(new_pw) >= 6:
                                import bcrypt as _bcrypt
                                hashed = _bcrypt.hashpw(new_pw.encode(), _bcrypt.gensalt()).decode()
                                db_update(TBL_USERS, "user_id", u["user_id"], {
                                    "password_hash":            hashed,
                                    "must_change_password":     "yes",
                                    "password_reset_requested": "no",
                                    "reset_requested_at":       None,
                                })
                                st.success(f"✅ Password reset for {u['email']}. They must change it on next login.")
                                st.rerun()
                            else:
                                st.error("Password must be at least 6 characters.")
                    st.markdown("---")

    # ── All Users ──
    with tab6:
        section_header("👥 All Registered Users")
        display_cols = [c for c in ["business_name","full_name","email","phone","plan_type",
                                    "plan_status","subscription_end","created_at"]
                        if c in users_df.columns]
        st.dataframe(users_df[display_cols].rename(columns={
            "business_name":   "Business",
            "full_name":       "Name",
            "email":           "Email",
            "phone":           "Phone",
            "plan_type":       "Plan",
            "plan_status":     "Status",
            "subscription_end":"Expires",
            "created_at":      "Joined",
        }), width='stretch')

    # ── Deactivated ──
    with tab7:
        deact_df = users_df[users_df["plan_status"] == "expired"]
        if deact_df.empty:
            st.info("No deactivated users.")
        else:
            for _, u in deact_df.iterrows():
                col1, col2 = st.columns([3,2])
                with col1:
                    st.markdown(f"**{u['business_name']}** — {u['email']}")
                    st.caption(f"📧 {u['email']} | 📱 {u.get('phone','—')} | Plan: {u['plan_type']} | Expired: {u.get('subscription_end','?')}")
                with col2:
                    react_plan = st.selectbox(
                        "Plan", ["monthly", "yearly"],
                        index=0 if u.get("plan_type","monthly") == "monthly" else 1,
                        key=f"react_plan_{u['user_id']}",
                        label_visibility="collapsed"
                    )
                    days       = 365 if react_plan == "yearly" else 30
                    end_dt     = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                    pay_amount = (PAYMENT_DETAILS["yearly_price"] if react_plan == "yearly"
                                  else PAYMENT_DETAILS["monthly_price"])
                    react_label = "1 Year" if react_plan == "yearly" else "30 Days"
                    if st.button(f"🔁 Reactivate ({react_label})", key=f"react_{u['user_id']}"):
                        db_update(TBL_USERS, "user_id", u["user_id"], {
                            "plan_status":        "active",
                            "plan_type":          react_plan,
                            "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                            "subscription_end":   end_dt,
                        })
                        log_payment(u["user_id"], u["business_name"], u["email"],
                                    react_plan, pay_amount, "Reactivation")
                        st.success(f"✅ {u['business_name']} reactivated ({react_plan}) until {end_dt}")
                        st.rerun()
                st.markdown("---")

    # ── User Activity ──
    with tab8:
        st.markdown("#### 👁️ User Activity Monitor")
        st.caption("Live view of who is active, at-risk, or ghost across trial and paid users.")

        now_dt = datetime.now()
        rows = []
        for _, u in users_df.iterrows():
            biz_name    = u.get("business_name", "—")
            email       = u.get("email", "—")
            status      = u.get("plan_status", "—")
            plan        = u.get("plan_type", "—")
            last_login  = u.get("last_login")
            total_txns  = int(u.get("total_transactions") or 0)
            trial_start = u.get("subscription_start")

            # Trial day
            if status == "active" and trial_start:
                try:
                    ts = datetime.strptime(str(trial_start)[:10], "%Y-%m-%d")
                    trial_label = f"Day {(now_dt - ts).days + 1}"
                except Exception:
                    trial_label = "—"
            else:
                trial_label = "—"

            # Last login label + days since
            if last_login:
                try:
                    ll   = datetime.fromisoformat(str(last_login)[:19])
                    diff = (now_dt - ll).days
                    login_label = "Today" if diff == 0 else ("Yesterday" if diff == 1 else f"{diff}d ago")
                    login_days  = diff
                except Exception:
                    login_label = "—"; login_days = 999
            else:
                login_label = "Never"; login_days = 999

            # Health signal
            if login_days == 999:
                health = "👻 Ghost"
            elif login_days <= 1:
                health = "🟢 Active"
            elif login_days <= 3:
                health = "🟡 Quiet"
            else:
                health = "🔴 At Risk"

            rows.append({
                "Business":     biz_name,
                "Email":        email,
                "Status":       status,
                "Plan":         plan,
                "Trial Day":    trial_label,
                "Last Login":   login_label,
                "Transactions": total_txns,
                "Health":       health,
                "_login_days":  login_days,
            })

        activity_df = pd.DataFrame(rows)

        # Summary KPIs
        k1, k2, k3, k4 = st.columns(4)
        with k1: kpi_card("Total Users",  str(len(activity_df)),                                   "All registered",   icon="👥")
        with k2: kpi_card("Active Today", str(len(activity_df[activity_df["Health"] == "🟢 Active"])), "Logged in ≤1 day", icon="🟢")
        with k3: kpi_card("At Risk",      str(len(activity_df[activity_df["Health"] == "🔴 At Risk"])), "Silent 4+ days",  icon="🔴")
        with k4: kpi_card("Ghosts",       str(len(activity_df[activity_df["Health"] == "👻 Ghost"])),  "Never logged in",  icon="👻")

        st.markdown("---")

        # Filter
        f_col, _ = st.columns([2, 4])
        with f_col:
            health_filter = st.selectbox(
                "Filter by health",
                ["All", "🟢 Active", "🟡 Quiet", "🔴 At Risk", "👻 Ghost"],
                key="activity_health_filter"
            )

        display_df = activity_df.copy()
        if health_filter != "All":
            display_df = display_df[display_df["Health"] == health_filter]
        display_df = display_df.sort_values("_login_days").drop(columns=["_login_days"])

        if display_df.empty:
            st.info("No users match this filter.")
        else:
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Business":     st.column_config.TextColumn("Business",  width="medium"),
                    "Email":        st.column_config.TextColumn("Email",     width="medium"),
                    "Status":       st.column_config.TextColumn("Status",    width="small"),
                    "Plan":         st.column_config.TextColumn("Plan",      width="small"),
                    "Trial Day":    st.column_config.TextColumn("Trial Day", width="small"),
                    "Last Login":   st.column_config.TextColumn("Last Login",width="small"),
                    "Transactions": st.column_config.NumberColumn("Sales",   width="small"),
                    "Health":       st.column_config.TextColumn("Health",    width="small"),
                }
            )

        # Action nudges
        st.markdown("---")
        st.markdown("#### 💡 Who to reach out to today")
        priority_df = activity_df[
            activity_df["Health"].isin(["👻 Ghost", "🔴 At Risk"])
        ].sort_values("_login_days", ascending=False).drop(columns=["_login_days"])

        if priority_df.empty:
            st.success("✅ All users have been active recently. Nothing urgent.")
        else:
            for _, row in priority_df.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"**{row['Business']}** — {row['Email']}")
                        st.caption(
                            f"{row['Health']} · Last login: {row['Last Login']} · "
                            f"Sales recorded: {row['Transactions']} · "
                            f"Plan: {row['Plan']} · Status: {row['Status']}"
                        )
                    with c2:
                        st.markdown("📲 WhatsApp")
