# ============================================================
#  pages/page_dashboard.py
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


def page_dashboard():
    user        = st.session_state.user
    business_id = user["business_id"]
    now         = datetime.now()
    hour        = now.hour
    greeting    = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    first_name  = user.get("full_name", "there").split()[0]

    st.markdown(f"""
<div style="
background:linear-gradient(135deg,#0D1117 0%,#111827 100%);
border:1px solid #1F2D3D;border-radius:18px;
padding:1.75rem 2rem;margin-bottom:1.5rem;
position:relative;overflow:hidden;
">
<div style="
position:absolute;top:-40px;right:-40px;
width:200px;height:200px;border-radius:50%;
background:rgba(245,166,35,0.06);
"></div>
<div style="font-size:0.7rem;color:#4A6080;text-transform:uppercase;
letter-spacing:0.12em;font-weight:600;margin-bottom:0.4rem;
font-family:'DM Mono',monospace;">
{now.strftime("%A, %d %B %Y")}
</div>
<div style="
font-family:'Syne',sans-serif;
font-size:1.55rem;font-weight:800;color:#F0F4F8;
letter-spacing:-0.04em;margin-bottom:0.25rem;
">{greeting}, {first_name} 👋</div>
<div style="font-size:0.875rem;color:#4A6080;">
Here's your business snapshot for
<strong style="color:#8BA0B8;">{user.get("business_name","your business")}</strong>
</div>
</div>
    """, unsafe_allow_html=True)

    with st.spinner("Loading your data…"):
        sales_df    = get_sales_df(business_id)
        products_df = get_products_df(business_id)
        expenses_df = get_expenses_df(business_id)
        kpis        = compute_kpis(sales_df, expenses_df)

    # ── 4 Core KPIs ──
    if not products_df.empty:
        low_count = len(products_df[
            products_df["stock_quantity"] <= products_df["reorder_level"]
        ])
    else:
        low_count = 0

    growth = kpis["week_growth"]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Today's Revenue", fmt_naira(kpis["today_revenue"]),
                 f"{kpis['today_txn']} transactions today")
    with c2:
        kpi_card("This Week", fmt_naira(kpis["week_revenue"]),
                 f"{'\u25b2' if growth >= 0 else '\u25bc'} {abs(growth):.1f}% vs last week",
                 positive=(growth >= 0))
    with c3:
        kpi_card("Net Profit (Month)", fmt_naira(kpis["net_profit"]),
                 f"After \u20a6{kpis['month_expenses']:,.0f} expenses",
                 positive=(kpis["net_profit"] >= 0))
    with c4:
        kpi_card("Low Stock Alerts", str(low_count),
                 "Products need restocking" if low_count > 0 else "All products stocked",
                 positive=(low_count == 0))
    # ── Charts ──
    if not sales_df.empty:
        col_left, col_right = st.columns([3, 2])

        with col_left:
            section_header("Revenue Trend — Last 30 Days")
            trend_df = sales_df.copy()
            trend_df["date"] = trend_df["sale_date"].dt.date
            # Fill every day in the last 30 days so missing days show as 0
            last30 = trend_df[trend_df["sale_date"] >= (datetime.now() - timedelta(days=30))]
            daily = last30.groupby("date")["total_amount"].sum().reset_index()
            all_dates = pd.date_range(
                end=datetime.now().date(),
                periods=30, freq="D"
            ).date
            daily = (
                daily.set_index("date")
                .reindex(all_dates, fill_value=0)
                .reset_index()
                .rename(columns={"index": "date"})
            )
            daily["date_str"] = pd.to_datetime(daily["date"]).dt.strftime("%d %b")
            if not daily.empty:
                avg_rev = daily["total_amount"].mean()
                fig = go.Figure()
                # Bar for each day
                fig.add_trace(go.Bar(
                    x=daily["date_str"],
                    y=daily["total_amount"],
                    marker_color=[
                        "#F5A623" if v >= avg_rev else "#6366f1"
                        for v in daily["total_amount"]
                    ],
                    hovertemplate="%{x}<br>₦%{y:,.0f}<extra></extra>",
                ))
                # Average line
                fig.add_hline(
                    y=avg_rev,
                    line_dash="dot",
                    line_color="#00C896",
                    line_width=1.5,
                    annotation_text=f"Avg ₦{avg_rev:,.0f}",
                    annotation_position="top right",
                    annotation_font_size=11,
                    annotation_font_color="#00C896",
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=20, b=0),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(
                        tickprefix="₦",
                        gridcolor="rgba(255,255,255,0.06)",
                        tickfont=dict(size=11),
                        tickformat=",.0f",
                    ),
                    xaxis=dict(
                        type="category",
                        tickangle=-45,
                        tickfont=dict(size=10),
                        gridcolor="rgba(0,0,0,0)",
                        nticks=10,
                    ),
                    height=240,
                    bargap=0.25,
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption("■ Gold bars = above average days  ■ Purple = below average")

        with col_right:
            section_header("Sales by Payment Method")
            pm_df = (
                sales_df.groupby("payment_method")["total_amount"]
                .sum().reset_index()
            )
            if not pm_df.empty:
                fig2 = px.pie(
                    pm_df, values="total_amount", names="payment_method",
                    color_discrete_sequence=["#6366f1","#10b981","#f59e0b","#ef4444"],
                    hole=0.55,
                )
                fig2.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=280,
                    legend=dict(orientation="h", y=-0.1),
                )
                st.plotly_chart(fig2, use_container_width=True)

        # Top products
        section_header("Top Selling Products (by Revenue)")
        top_df = (
            sales_df.groupby("product_name")["total_amount"]
            .sum().reset_index()
            .sort_values("total_amount", ascending=True)
            .tail(8)
        )
        if not top_df.empty:
            fig3 = px.bar(
                top_df, x="total_amount", y="product_name",
                orientation="h",
                labels={"total_amount": "Revenue (₦)", "product_name": ""},
                color_discrete_sequence=["#6366f1"],
            )
            fig3.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(tickprefix="₦", gridcolor="#f1f5f9"),
                height=300,
            )
            st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("📭 No sales data yet. Record your first sale to see analytics here.")

    # ── Low Stock Alerts ──
    if not products_df.empty:
        low_stock = products_df[
            products_df["stock_quantity"] <= products_df["reorder_level"]
        ]
        if not low_stock.empty:
            section_header("⚠️ Low Stock Alerts")
            for _, row in low_stock.iterrows():
                qty = safe_int(row["stock_quantity"])
                lvl = safe_int(row["reorder_level"])
                css = "alert-critical" if qty <= 0 else "alert-low"
                st.markdown(
                    f'<div class="{css}">🔔 <strong>{row["product_name"]}</strong> — '
                    f'{qty} units left (reorder level: {lvl})</div>',
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────
#  PAGE: RECORD SALE
# ─────────────────────────────────────────────

