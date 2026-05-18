# ============================================================
#  pages/page_insights.py
# ============================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shared import *
import string
import secrets
import bcrypt
import re
import io
import urllib.parse


def page_insights():
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("🧠 Business Insights", "Data-driven intelligence for smarter decisions")

    with st.spinner("Crunching your numbers…"):
        sales_df    = get_sales_df(business_id)
        products_df = get_products_df(business_id)
        expenses_df = get_expenses_df(business_id)
        insights    = compute_insights(sales_df, products_df, expenses_df)

    if sales_df.empty:
        st.info("📭 No data yet. Record some sales to unlock insights.")
        return

    # ── Summary Stats ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Avg Daily Revenue",
                 fmt_naira(insights["avg_daily_revenue"]), "Based on all recorded days")
    with c2:
        kpi_card("Best Sales Day", insights.get("best_day", "N/A"), "Highest revenue weekday")
    with c3:
        kpi_card("Slowest Day", insights.get("worst_day", "N/A"), "Lowest revenue weekday")
    with c4:
        if not insights["top_products_revenue"].empty:
            best = insights["top_products_revenue"].iloc[0]["product_name"]
        else:
            best = "N/A"
        kpi_card("Best Seller", best, "By total revenue")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Trends", "🏆 Products", "📦 Inventory", "📅 Weekday", "📊 Export"
    ])

    # ── Tab 1: Trends ──
    with tab1:
        section_header("Monthly Performance Comparison")

        # ── Build monthly aggregates from sales ──
        if not sales_df.empty:
            ms = sales_df.copy()
            ms["sale_date"] = pd.to_datetime(ms["sale_date"], errors="coerce", utc=True).dt.tz_localize(None)
            ms = ms.dropna(subset=["sale_date"])
            ms["year"]  = ms["sale_date"].dt.year
            ms["month"] = ms["sale_date"].dt.month
            ms["month_label"] = ms["sale_date"].dt.strftime("%b %Y")
            ms["month_sort"]  = ms["sale_date"].dt.to_period("M")

            # ── Filters ──
            available_years = sorted(ms["year"].unique().tolist(), reverse=True)
            tf1, tf2, tf3 = st.columns(3)
            selected_year = tf1.selectbox(
                "Year", ["All years"] + [str(y) for y in available_years], key="ins_year"
            )
            metric_choice = tf2.selectbox(
                "Metric", ["Revenue & Profit", "Revenue only", "Profit only", "All (Revenue, Cost, Profit)"],
                key="ins_metric"
            )
            num_months = tf3.slider("Last N months", min_value=3, max_value=24, value=12, key="ins_months")

            # Apply year filter
            if selected_year != "All years":
                ms = ms[ms["year"] == int(selected_year)]

            # Monthly aggregation
            monthly = (
                ms.groupby(["month_sort", "month_label"])
                .agg(
                    revenue  =("total_amount", "sum"),
                    cost     =("cost_total",   "sum"),
                    profit   =("gross_profit",  "sum"),
                    txn_count=("sale_id",       "count"),
                )
                .reset_index()
                .sort_values("month_sort")
            )

            # Add monthly expenses
            if not expenses_df.empty:
                ex = expenses_df.copy()
                ex["expense_date"] = pd.to_datetime(ex["expense_date"], errors="coerce", utc=True).dt.tz_localize(None)
                ex = ex.dropna(subset=["expense_date"])
                ex["month_sort"]  = ex["expense_date"].dt.to_period("M")
                ex["month_label"] = ex["expense_date"].dt.strftime("%b %Y")
                monthly_exp = (
                    ex.groupby("month_sort")["amount"].sum()
                    .reset_index().rename(columns={"amount": "expenses"})
                )
                monthly = monthly.merge(monthly_exp, on="month_sort", how="left")
                monthly["expenses"] = monthly["expenses"].fillna(0)
                monthly["net_profit"] = monthly["profit"] - monthly["expenses"]
            else:
                monthly["expenses"]   = 0
                monthly["net_profit"] = monthly["profit"]

            # Limit to last N months
            monthly = monthly.tail(num_months)

            if monthly.empty:
                st.info("No data for the selected filters.")
            else:
                # ── Summary KPIs ──
                best_rev_row  = monthly.loc[monthly["revenue"].idxmax()]
                best_prof_row = monthly.loc[monthly["net_profit"].idxmax()]
                if len(monthly) >= 2:
                    last_rev  = monthly.iloc[-1]["revenue"]
                    prev_rev  = monthly.iloc[-2]["revenue"]
                    mom_growth = ((last_rev - prev_rev) / prev_rev * 100) if prev_rev else 0
                else:
                    mom_growth = 0

                sk1, sk2, sk3, sk4 = st.columns(4)
                with sk1:
                    kpi_card("Best Month (Revenue)", best_rev_row["month_label"],
                             fmt_naira(best_rev_row["revenue"]))
                with sk2:
                    kpi_card("Best Month (Profit)", best_prof_row["month_label"],
                             fmt_naira(best_prof_row["net_profit"]))
                with sk3:
                    kpi_card("Latest Month Growth",
                             f"{'▲' if mom_growth >= 0 else '▼'} {abs(mom_growth):.1f}%",
                             f"vs previous month", positive=(mom_growth >= 0))
                with sk4:
                    kpi_card("Period Total", fmt_naira(monthly["revenue"].sum()),
                             f"{int(monthly['txn_count'].sum())} transactions")

                st.markdown("---")

                # ── Grouped bar chart ──
                fig = go.Figure()
                x_labels = monthly["month_label"].tolist()

                if metric_choice in ["Revenue & Profit", "Revenue only", "All (Revenue, Cost, Profit)"]:
                    fig.add_trace(go.Bar(
                        name="Revenue",
                        x=x_labels,
                        y=monthly["revenue"],
                        marker_color="#6366f1",
                        hovertemplate="%{x}<br>Revenue: ₦%{y:,.0f}<extra></extra>",
                    ))

                if metric_choice == "All (Revenue, Cost, Profit)":
                    fig.add_trace(go.Bar(
                        name="Cost",
                        x=x_labels,
                        y=monthly["cost"],
                        marker_color="#ef4444",
                        hovertemplate="%{x}<br>Cost: ₦%{y:,.0f}<extra></extra>",
                    ))

                if metric_choice in ["Revenue & Profit", "Profit only", "All (Revenue, Cost, Profit)"]:
                    fig.add_trace(go.Bar(
                        name="Net Profit",
                        x=x_labels,
                        y=monthly["net_profit"],
                        marker_color="#00C896",
                        hovertemplate="%{x}<br>Net Profit: ₦%{y:,.0f}<extra></extra>",
                    ))

                fig.update_layout(
                    barmode="group",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=20, b=0),
                    height=320,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom", y=1.02,
                        xanchor="right",  x=1,
                        font=dict(size=11),
                    ),
                    xaxis=dict(
                        type="category",
                        tickangle=-45,
                        tickfont=dict(size=10),
                        gridcolor="rgba(0,0,0,0)",
                    ),
                    yaxis=dict(
                        tickprefix="₦",
                        tickformat=",.0f",
                        gridcolor="rgba(255,255,255,0.06)",
                        tickfont=dict(size=11),
                    ),
                    bargap=0.2,
                    bargroupgap=0.05,
                )
                st.plotly_chart(fig, use_container_width=True)

                # ── Monthly data table ──
                with st.expander("📋 View monthly breakdown table"):
                    display_monthly = monthly[["month_label","revenue","cost","profit","expenses","net_profit","txn_count"]].copy()
                    display_monthly.columns = ["Month","Revenue","Cost","Gross Profit","Expenses","Net Profit","Transactions"]
                    for col in ["Revenue","Cost","Gross Profit","Expenses","Net Profit"]:
                        display_monthly[col] = display_monthly[col].apply(fmt_naira)
                    st.dataframe(display_monthly, use_container_width=True, hide_index=True)
        else:
            st.info("No sales data yet to build monthly comparison.")

        # ── Category Performance ──
        st.markdown("---")
        section_header("Category Performance")
        if not insights["category_revenue"].empty:
            cat_fig = px.bar(
                insights["category_revenue"].sort_values("total_amount"),
                x="total_amount", y="category",
                orientation="h",
                labels={"total_amount": "Revenue (₦)", "category": ""},
                color_discrete_sequence=["#F5A623"],
            )
            cat_fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                height=max(200, len(insights["category_revenue"]) * 45),
                xaxis=dict(tickprefix="₦", tickformat=",.0f",
                           gridcolor="rgba(255,255,255,0.06)"),
                yaxis=dict(tickfont=dict(size=12)),
            )
            st.plotly_chart(cat_fig, use_container_width=True)
        else:
            st.info("No category data yet.")

    # ── Tab 2: Products ──
    with tab2:
        col_l, col_r = st.columns(2)
        with col_l:
            section_header("Top Products by Revenue")
            if not insights["top_products_revenue"].empty:
                fig = px.bar(
                    insights["top_products_revenue"].sort_values("total_amount"),
                    x="total_amount", y="product_name", orientation="h",
                    labels={"total_amount": "Revenue (₦)", "product_name": ""},
                    color_discrete_sequence=["#6366f1"],
                )
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0), height=350,
                    xaxis=dict(tickprefix="₦"),
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_r:
            section_header("Top Products by Quantity Sold")
            if not insights["top_products_qty"].empty:
                fig2 = px.bar(
                    insights["top_products_qty"].sort_values("quantity"),
                    x="quantity", y="product_name", orientation="h",
                    labels={"quantity": "Units Sold", "product_name": ""},
                    color_discrete_sequence=["#10b981"],
                )
                fig2.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0), height=350,
                )
                st.plotly_chart(fig2, use_container_width=True)

        section_header("⚠️ Slow-Moving Products (Last 30 Days)")
        if not insights["slow_movers"].empty:
            st.dataframe(
                insights["slow_movers"].rename(
                    columns={"product_name":"Product","quantity":"Units Sold (30d)"}
                ),
                use_container_width=True,
            )
        else:
            st.markdown('<div class="alert-success">✅ All products are selling at healthy rates.</div>',
                        unsafe_allow_html=True)

    # ── Tab 3: Inventory ──
    with tab3:
        section_header("🔴 Low Stock Products")
        if not insights["low_stock"].empty:
            for _, r in insights["low_stock"].iterrows():
                qty = safe_int(r["stock_quantity"])
                css = "alert-critical" if qty <= 0 else "alert-low"
                st.markdown(
                    f'<div class="{css}">⚠️ <strong>{r["product_name"]}</strong> '
                    f'— {qty} units left (reorder at {safe_int(r["reorder_level"])})</div>',
                    unsafe_allow_html=True
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
                use_container_width=True,
            )
        else:
            st.info("Not enough sales history to project stockout dates.")

    # ── Tab 4: Weekday ──
    with tab4:
        section_header("Revenue by Day of Week")
        if not insights["weekday_performance"].empty:
            wd = insights["weekday_performance"]
            colors = ["#ef4444" if r == wd["revenue"].min()
                      else ("#10b981" if r == wd["revenue"].max() else "#6366f1")
                      for r in wd["revenue"]]
            fig = go.Figure(go.Bar(
                x=wd["weekday"], y=wd["revenue"],
                marker_color=colors,
                text=[fmt_naira(v) for v in wd["revenue"]],
                textposition="outside",
            ))
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(tickprefix="₦", gridcolor="#f1f5f9"),
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)

            if insights["best_day"] and insights["worst_day"]:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        f'<div class="alert-success">🏆 <strong>Best day:</strong> '
                        f'{insights["best_day"]} — schedule more staff and stock up.</div>',
                        unsafe_allow_html=True
                    )
                with col2:
                    st.markdown(
                        f'<div class="alert-low">💡 <strong>Slowest day:</strong> '
                        f'{insights["worst_day"]} — consider promotions or discounts.</div>',
                        unsafe_allow_html=True
                    )

    # ── Tab 5: Export ──
    with tab5:
        section_header("📥 Download Your Data")
        col1, col2, col3 = st.columns(3)

        with col1:
            if not sales_df.empty:
                csv = sales_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Download Sales CSV",
                    data=csv, file_name="sales_export.csv",
                    mime="text/csv", use_container_width=True,
                )

        with col2:
            if not products_df.empty:
                csv = products_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Download Products CSV",
                    data=csv, file_name="products_export.csv",
                    mime="text/csv", use_container_width=True,
                )

        with col3:
            if not expenses_df.empty:
                csv = expenses_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Download Expenses CSV",
                    data=csv, file_name="expenses_export.csv",
                    mime="text/csv", use_container_width=True,
                )


# ─────────────────────────────────────────────
#  PAGE: ADMIN PANEL
# ─────────────────────────────────────────────

