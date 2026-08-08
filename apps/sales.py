"""
pages/sales.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Sales Management App
══════════════════════════════════════════════════════════════════════

Pages contained in this module:
  • Dashboard      — KPI cards, 30-day revenue chart, top products
  • Record Sale    — multi-item cart, negotiated prices, PDF receipt
  • Sales History  — date filter, edit, void with stock reconciliation

Cross-app links:
  • Low-stock alert on the dashboard links to Inventory app
  • Dashboard net profit card pulls expenses via shared.db.compute_kpis
"""

import io
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shared.db import (
    get_supabase,
    get_sales_df, get_products_df, get_products_df_live, get_expenses_df,
    get_sale_items_df, get_products_by_ids, search_products,
    get_debts_df, get_customer_directory,
    compute_kpis,
    db_fetch, db_insert, db_insert_many, db_update, db_delete, clear_table_cache,
    log_activity, log_cashbook_entry,
    TBL_SALES, TBL_SALE_ITEMS, TBL_PRODUCTS, TBL_DEBTS, TBL_CASHBOOK,
    gen_id, fmt_naira, safe_float, safe_int, fmt_qty,
)
from shared.theme import apply_suite_css, kpi_card, section_header, page_header, chart_layout, chart_config, CHART_GOLD, CHART_JADE, CHART_INDIGO, CHART_RUBY, CHART_PALETTE
from shared.auth import verify_void_pin, has_void_pin


def _restore_stock_amount(product_row, sale_item):
    """
    Compute the correct stock_quantity after voiding a sale line.

    Bug this fixes: sale_items.quantity is recorded in whatever unit the
    sale was made in (e.g. 6 pieces, when the product is sold by sub-unit),
    while products.stock_quantity is always tracked in BASE units and can be
    fractional (e.g. 6.5 bags left after selling 6 of 12 pieces-per-bag).
    The old code did `int(stock_quantity) + int(quantity)` — mixing units
    and truncating the fraction — so voiding a 6-piece sale against 6.5
    bags on hand produced 6 + 6 = 12 bags instead of the correct 7 bags.

    Fix: prefer the base-unit amount that was actually deducted at sale
    time (sale_items.stock_deduct, persisted going forward). For older
    sales recorded before this fix (no stock_deduct column populated),
    fall back to converting the sold quantity into base units using the
    product's current units_per_pack and recorded sell_mode.
    """
    current_stock = safe_float(product_row["stock_quantity"])
    upp = safe_int(product_row.get("units_per_pack", 1)) or 1

    stock_deduct = sale_item.get("stock_deduct", None)
    if stock_deduct is not None and str(stock_deduct) != "" and not pd.isna(stock_deduct):
        restore_amt = safe_float(stock_deduct)
    else:
        # Legacy fallback for sales recorded before stock_deduct existed.
        qty = safe_float(sale_item.get("quantity", 0))
        sell_mode = sale_item.get("sell_mode", "base")
        restore_amt = (qty / upp) if sell_mode == "sub" else qty

    new_stock = current_stock + restore_amt

    # Keep fractional stock for sub-unit products, whole numbers only
    # for products sold strictly in full packs — mirrors the same rule
    # used when stock is originally deducted during a sale.
    if upp > 1:
        return round(max(0.0, new_stock), 4)
    return int(max(0, round(new_stock)))


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]
    now         = datetime.now()
    hour        = now.hour
    greeting    = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    first_name  = user.get("full_name", "there").split()[0]

    st.markdown(f"""
<div style="
  background:linear-gradient(135deg,#0D1117 0%,#111827 100%);
  border:1px solid #1F2D3D; border-radius:18px;
  padding:1.75rem 2rem; margin-bottom:1.5rem;
  position:relative; overflow:hidden;
">
<div style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;
  border-radius:50%;background:rgba(245,166,35,0.06);"></div>
<div style="font-size:0.7rem;color:#4A6080;text-transform:uppercase;
  letter-spacing:0.12em;font-weight:600;margin-bottom:0.4rem;
  font-family:'DM Mono',monospace;">{now.strftime("%A, %d %B %Y")}</div>
<div style="font-family:'Syne',sans-serif;font-size:1.55rem;font-weight:800;
  color:#F0F4F8;letter-spacing:-0.04em;margin-bottom:0.25rem;">
  {greeting}, {first_name} 👋</div>
<div style="font-size:0.875rem;color:#4A6080;">
  Here's your business snapshot for
  <strong style="color:#8BA0B8;">{user.get("business_name","your business")}</strong>
</div>
</div>
    """, unsafe_allow_html=True)

    with st.spinner("Loading your data…"):
        sales_df    = get_sales_df(business_id)
        products_df = get_products_df_live(business_id)  # live — alerts must be accurate
        expenses_df = get_expenses_df(business_id)
        kpis        = compute_kpis(sales_df, expenses_df)

    # Low-stock count (cross-app bridge to Inventory)
    if not products_df.empty:
        low_count = len(products_df[products_df["stock_quantity"] <= products_df["reorder_level"]])
    else:
        low_count = 0

    growth = kpis["week_growth"]
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Today's Revenue", fmt_naira(kpis["today_revenue"]),
                 f"{kpis['today_txn']} transactions today", icon="💰")
        # Cash transparency breakdown
        collected       = kpis["today_collected"]
        credit_extended = kpis["today_credit_extended"]
        if credit_extended > 0:
            st.markdown(
                f"""
<div style="background:#0D1117;border:1px solid #1F2D3D;border-radius:10px;
  padding:0.6rem 0.85rem;margin-top:-0.5rem;margin-bottom:0.5rem;font-size:0.78rem;">
  <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
    <span style="color:#4A6080;">✅ Fully Collected</span>
    <span style="color:#10B981;font-weight:700;">{fmt_naira(collected)}</span>
  </div>
  <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
    <span style="color:#4A6080;">📕 Total Credit </span>
    <span style="color:#F59E0B;font-weight:700;">{fmt_naira(credit_extended)}</span>
  </div>
  <div style="border-top:1px solid #1F2D3D;margin-top:0.3rem;padding-top:0.3rem;
    display:flex;justify-content:space-between;">
    <span style="color:#4A6080;">💰 Total Sales Value</span>
    <span style="color:#8BA0B8;font-weight:700;">{fmt_naira(kpis['today_revenue'])}</span>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
<div style="background:#0D1117;border:1px solid #1F2D3D;border-radius:10px;
  padding:0.5rem 0.85rem;margin-top:-0.5rem;margin-bottom:0.5rem;font-size:0.78rem;">
  <div style="display:flex;justify-content:space-between;">
    <span style="color:#4A6080;">✅ All Payment Fully collected</span>
    <span style="color:#10B981;font-weight:700;">{fmt_naira(collected)}</span>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )
    with c2:
        kpi_card("This Week", fmt_naira(kpis["week_revenue"]),
                 f"{'▲' if growth >= 0 else '▼'} {abs(growth):.1f}% vs last week",
                 positive=(growth >= 0), icon="📈")
    c3, c4 = st.columns(2)
    with c3:
        kpi_card("Net Profit (Month)", fmt_naira(kpis["net_profit"]),
                 f"After {st.session_state.get("currency_symbol","₦")}{kpis['month_expenses']:,.0f} expenses",
                 positive=(kpis["net_profit"] >= 0), icon="📊")
    with c4:
        kpi_card("Low Stock Alerts", str(low_count),
                 "Products need restocking" if low_count > 0 else "All products stocked",
                 positive=(low_count == 0),
                 icon="⚠️" if low_count > 0 else "✅")
        if low_count > 0:
            if st.button("→ Go to Inventory", key="dash_goto_inv", width='stretch'):
                st.session_state.current_page = "inventory"
                st.rerun()

    # ── Charts ──
    if not sales_df.empty:
        with st.expander("📈 Revenue Trend — Last 30 Days", expanded=False):
          col_left, col_right = st.columns([3, 2])

          with col_left:
            section_header("Revenue Trend — Last 30 Days")
            trend_df = sales_df.copy()
            last30   = trend_df[trend_df["sale_date"] >= (now - timedelta(days=30))]
            daily    = last30.groupby(last30["sale_date"].dt.date)["total_amount"].sum().reset_index()
            daily.columns = ["date", "total_amount"]
            all_dates = pd.date_range(end=now.date(), periods=30, freq="D").date
            daily = (
                daily.set_index("date")
                .reindex(all_dates, fill_value=0)
                .reset_index()
                .rename(columns={"index": "date"})
            )
            daily["date_str"] = pd.to_datetime(daily["date"]).dt.strftime("%d %b")
            avg_rev = daily["total_amount"].mean()
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=daily["date_str"], y=daily["total_amount"],
                marker_color=[CHART_GOLD if v >= avg_rev else CHART_INDIGO for v in daily["total_amount"]],
                marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>" + st.session_state.get("currency_symbol","₦") + "%{y:,.0f}<extra></extra>",
            ))
            fig.add_hline(y=avg_rev, line_dash="dot", line_color=CHART_JADE, line_width=1.5,
                          annotation_text=f"Avg {st.session_state.get("currency_symbol","₦")}{avg_rev:,.0f}",
                          annotation_position="top right",
                          annotation_font_size=11, annotation_font_color=CHART_JADE)
            fig.update_layout(**chart_layout(
                height=260,
                margin=dict(l=0, r=10, t=20, b=0),
                bargap=0.3, showlegend=False,
                xaxis=dict(type="category", tickangle=-45, tickfont=dict(size=10),
                           gridcolor="rgba(0,0,0,0)", nticks=10),
                yaxis=dict(tickprefix=st.session_state.get("currency_symbol","₦"), tickformat=",.0f"),
            ))
            st.plotly_chart(fig, config=chart_config(), width='stretch')
            st.caption("■ Gold = above average  ■ Indigo = below average")

          with col_right:
            section_header("Sales by Payment Method")
            pm_df = sales_df.groupby("payment_method")["total_amount"].sum().reset_index()
            if not pm_df.empty:
                fig2 = px.pie(pm_df, values="total_amount", names="payment_method",
                              color_discrete_sequence=CHART_PALETTE,
                              hole=0.6)
                fig2.update_traces(
                    textposition="outside",
                    textinfo="percent",
                    textfont=dict(size=12),
                    pull=[0.03] * len(pm_df),
                    hovertemplate="<b>%{label}</b><br>" + st.session_state.get("currency_symbol","₦") + "%{value:,.0f}<br>%{percent}<extra></extra>",
                )
                fig2.update_layout(**chart_layout(height=300, margin=dict(l=0,r=0,t=10,b=40)))
                st.plotly_chart(fig2, config=chart_config(), width='stretch')

        with st.expander("🏆 Top Selling Products", expanded=False):
            # Load sale_items for accurate per-product breakdown
            # (sales table stores concatenated names for multi-item sales)
            items_df = get_sale_items_df(business_id)

            if not items_df.empty:
                section_header("Top Selling Products (by Revenue)")
                top_rev_df = (
                    items_df.groupby("product_name")["line_total"]
                    .sum().reset_index()
                    .sort_values("line_total", ascending=True)
                    .tail(8)
                )
                if not top_rev_df.empty:
                    fig3 = px.bar(top_rev_df, x="line_total", y="product_name", orientation="h",
                                  labels={"line_total": "Revenue (" + st.session_state.get("currency_symbol","₦") + ")", "product_name": ""},
                                  color_discrete_sequence=[CHART_INDIGO])
                    fig3.update_traces(marker_line_width=0,
                                       hovertemplate="<b>%{y}</b><br>" + st.session_state.get("currency_symbol","₦") + "%{x:,.0f}<extra></extra>")
                    fig3.update_layout(**chart_layout(height=300,
                        xaxis=dict(tickprefix=st.session_state.get("currency_symbol","₦"), tickformat=",.0f")))
                    st.plotly_chart(fig3, config=chart_config(), width='stretch')

                section_header("By Quantity Sold")
                qty_col = "quantity" if "quantity" in items_df.columns else None
                if qty_col:
                    top_qty_df = (
                        items_df.groupby("product_name")[qty_col]
                        .sum().reset_index()
                        .sort_values(qty_col, ascending=True)
                        .tail(8)
                    )
                    fig4 = px.bar(top_qty_df, x=qty_col, y="product_name", orientation="h",
                                  labels={qty_col: "Units Sold", "product_name": ""},
                                  color_discrete_sequence=[CHART_JADE])
                    fig4.update_traces(marker_line_width=0,
                                       hovertemplate="<b>%{y}</b><br>%{x} units<extra></extra>")
                    fig4.update_layout(**chart_layout(height=300))
                    st.plotly_chart(fig4, config=chart_config(), width='stretch')
            else:
                st.info("No sales data yet for product breakdown.")
    else:
        st.info("📭 No sales yet. Record your first sale to see analytics here.")

    # ── Low-Stock Alerts ──
    if not products_df.empty:
        low_stock = products_df[products_df["stock_quantity"] <= products_df["reorder_level"]]
        if not low_stock.empty:
            section_header("⚠️ Low Stock Alerts")
            for _, row in low_stock.iterrows():
                qty = safe_int(row["stock_quantity"])
                css = "alert-critical" if qty <= 0 else "alert-low"
                st.markdown(
                    f'<div class="{css}">🔔 <strong>{row["product_name"]}</strong> — '
                    f'{qty} units left (reorder level: {safe_int(row["reorder_level"])})</div>',
                    unsafe_allow_html=True,
                )

    # ── Expiry Alerts (dashboard banner — critical & imminent only) ──────────
    if not products_df.empty and "expiry_date" in products_df.columns:
        from datetime import datetime as _dt
        _today    = pd.Timestamp(_dt.now().date())
        _dated    = products_df[products_df["expiry_date"].notna()].copy()
        if not _dated.empty:
            _dated["days_to_expiry"] = (_dated["expiry_date"] - _today).dt.days
            _banner_expired  = _dated[_dated["days_to_expiry"] < 0]
            _banner_soon     = _dated[
                (_dated["days_to_expiry"] >= 0) & (_dated["days_to_expiry"] <= 60)
            ]
            if not _banner_expired.empty or not _banner_soon.empty:
                section_header("🚨 Expiry Alerts")
            for _, r in _banner_expired.iterrows():
                days_ago = abs(int(r["days_to_expiry"]))
                exp_str  = pd.Timestamp(r["expiry_date"]).strftime("%d %b %Y")
                st.markdown(
                    f'<div class="alert-critical">❌ <strong>{r["product_name"]}</strong> '
                    f'EXPIRED {days_ago} day{"s" if days_ago != 1 else ""} ago ({exp_str}) — '
                    f'Remove from shelves immediately.</div>',
                    unsafe_allow_html=True,
                )
            for _, r in _banner_soon.iterrows():
                days_left = int(r["days_to_expiry"])
                exp_str   = pd.Timestamp(r["expiry_date"]).strftime("%d %b %Y")
                urgency   = "alert-critical" if days_left <= 14 else "alert-low"
                st.markdown(
                    f'<div class="{urgency}">⚠️ <strong>{r["product_name"]}</strong> '
                    f'expires in {days_left} day{"s" if days_left != 1 else ""} ({exp_str}).</div>',
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# RECORD SALE
# ══════════════════════════════════════════════════════════════════════════════

@st.fragment
def _build_cart_fragment(business_id):
    """
    Everything needed to search products and build the cart, isolated in
    its own fragment. Typing in the search box now only reruns THIS
    fragment, not the whole page (checkout panel, other sections) —
    unlike before, where every keystroke reran the entire page.
    Add-to-cart / remove-item already call st.rerun() explicitly below;
    inside a fragment that defaults to a FULL app rerun, so the checkout
    panel on the right still updates immediately when the cart changes —
    only pure typing (no rerun call) stays scoped to this fragment.
    """
    section_header("🛍️ Build Cart")
    # ── Product search ──────────────────────────────────────────
    # Initialise search query in session state so it persists across reruns
    if "cart_search" not in st.session_state:
        st.session_state.cart_search = ""

    st.session_state.cart_search = st.text_input(
        "🔍 Search product",
        value=st.session_state.cart_search,
        placeholder="Type any part of the product name…",
        key="cart_search_input",
    )

    query = st.session_state.cart_search.strip()
    # Indexed, bounded search — same cost whether the catalogue has 50
    # SKUs or 5,000, since Postgres does the filtering (not pandas) and
    # results are capped at 30. Empty/short query shows a small default
    # page instead of the whole catalogue, so the selectbox below never
    # has to render thousands of options.
    in_stock = search_products(business_id, query, limit=30, in_stock_only=True)

    if in_stock.empty:
        if query:
            st.warning(f"No in-stock products match \"{query}\".")
        else:
            st.warning("No products in stock. Add products in the Inventory app if you haven't yet.")
            if st.button("→ Go to Inventory"):
                st.session_state.current_page = "inventory"
                st.rerun()
    else:
        prod_names = in_stock["product_name"].tolist()
        sel_name   = st.selectbox("Product", prod_names, key="cart_prod")
        sel_prod_row = in_stock[in_stock["product_name"] == sel_name].iloc[0]

        # Unit config
        base_unit    = sel_prod_row.get("base_unit", "unit") or "unit"
        sub_unit     = sel_prod_row.get("sub_unit",  "unit") or "unit"
        upp          = safe_int(sel_prod_row.get("units_per_pack", 1)) or 1
        price_base   = safe_float(sel_prod_row["selling_price"])
        price_sub    = safe_float(sel_prod_row.get("selling_price_sub", 0))
        cost_price_u = safe_float(sel_prod_row["cost_price"])
        avail_base   = safe_float(sel_prod_row["stock_quantity"])   # always in base units

        # How much is already in cart (in base units)
        cart_reserved = sum(
            i["stock_deduct"] for i in st.session_state.cart
            if i["product_id"] == sel_prod_row["product_id"]
        )
        remaining_base = avail_base - cart_reserved

        # Unit selector — only show if product supports sub units
        if upp > 1 and price_sub > 0:
            sell_mode = st.radio(
                "Selling as",
                options=["base", "sub"],
                format_func=lambda x: (
                    f"Full {base_unit} — {fmt_naira(price_base)}"
                    if x == "base" else
                    f"Per {sub_unit} — {fmt_naira(price_sub)}"
                ),
                horizontal=True,
                key="cart_sell_mode",
            )
        else:
            sell_mode = "base"

        # Compute display availability based on mode
        if sell_mode == "sub":
            avail_display = remaining_base * upp
            unit_label    = sub_unit
            default_price = price_sub
            cost_per_unit = cost_price_u / upp
        else:
            avail_display = remaining_base
            unit_label    = base_unit
            default_price = price_base
            cost_per_unit = cost_price_u

        st.caption(
            f"📦 Listed price: **{fmt_naira(default_price)} per {unit_label}** "
            f"&nbsp;|&nbsp; 🏷️ Available: **{fmt_qty(avail_display)} {unit_label}s**"
            + (f" ({fmt_qty(remaining_base)} {base_unit}s)" if sell_mode == "sub" else "")
        )

        currency_sym = st.session_state.get("currency_symbol", "₦")
        pricing_mode = st.radio(
            "How do you want to enter the price?",
            options=["per_unit", "total"],
            format_func=lambda x: "Price per unit" if x == "per_unit" else "Total price for this line",
            horizontal=True,
            key="cart_pricing_mode",
            help=(
                "Use 'Total price for this line' when you've agreed a lump sum for multiple "
                "units (e.g. 3 for ₦500) instead of a clean per-unit rate — BizTrack will "
                "work out the per-unit rate for you."
            ),
        )

        with st.form("add_to_cart", clear_on_submit=True):
            ac1, ac2  = st.columns(2)
            sel_qty   = ac1.number_input(
                f"Quantity ({unit_label}s)",
                min_value=1, max_value=max(1, int(avail_display)), value=1, step=1,
            )

            if pricing_mode == "total":
                sel_total_price = ac2.number_input(
                    f"Total price for these {unit_label}s ({currency_sym})",
                    min_value=0.0, value=float(default_price), step=100.0,
                    help="Enter the full amount for this line — the per-unit rate is worked out automatically.",
                )
                sel_price = None
                listed_total = round(default_price * sel_qty, 2)
                if sel_total_price > listed_total:
                    st.warning(f"⚠️ Above listed total ({fmt_naira(listed_total)} for {sel_qty} {unit_label}s). Confirm?")
            else:
                sel_price = ac2.number_input(
                    f"Price per " + unit_label + " (" + currency_sym + ")",
                    min_value=0.0, value=float(default_price), step=100.0,
                    help="Change to override listed price",
                )
                sel_total_price = None
                if sel_price > default_price:
                    st.warning(f"⚠️ Above listed price ({fmt_naira(default_price)}). Confirm?")

            add_btn = st.form_submit_button("➕ Add to Cart", type="primary",
                                            width='stretch')

        if add_btn:
            prod_row   = in_stock[in_stock["product_name"] == sel_name].iloc[0]

            # Convert everything to base units for stock deduction
            if sell_mode == "sub":
                stock_deduct  = sel_qty / upp          # fractional base units
                cost_total    = round(cost_price_u * stock_deduct, 2)
                display_label = f"{sel_qty} {sub_unit}s"
            else:
                stock_deduct  = float(sel_qty)
                cost_total    = round(cost_price_u * sel_qty, 2)
                display_label = f"{sel_qty} {base_unit}s"

            if pricing_mode == "total":
                # Line total is exactly what the user typed — no per-unit rounding drift.
                line_total = round(float(sel_total_price), 2)
                negotiated = round(line_total / sel_qty, 6) if sel_qty else 0.0
                disc_amt   = max(0, round(default_price * sel_qty - line_total, 2))
            else:
                negotiated   = float(sel_price)
                line_total   = round(negotiated * sel_qty, 2)
                disc_amt     = max(0, round((default_price - negotiated) * sel_qty, 2))

            gross_profit = round(line_total - cost_total, 2)

            if stock_deduct > remaining_base:
                st.error(
                    f"Not enough stock. Available: {fmt_qty(avail_display)} {unit_label}s "
                    f"({remaining_base:.1f} {base_unit}s)."
                )
            else:
                merged = False
                # Only merge clean per-unit lines; total-price lines stay on their own
                # row so the exact typed amount is never re-multiplied/rounded.
                if pricing_mode == "per_unit":
                    for item in st.session_state.cart:
                        if (item["product_id"] == prod_row["product_id"] and
                                item["sell_mode"] == sell_mode and
                                item.get("pricing_mode", "per_unit") == "per_unit" and
                                item["negotiated_price"] == negotiated):
                            item["quantity"]     += int(sel_qty)
                            item["stock_deduct"] += stock_deduct
                            item["line_total"]    = round(negotiated * item["quantity"], 2)
                            item["cost_total"]    = round(cost_price_u * item["stock_deduct"], 2)
                            item["gross_profit"]  = round(item["line_total"] - item["cost_total"], 2)
                            item["discount_amt"]  = max(0, round((default_price - negotiated) * item["quantity"], 2))
                            merged = True
                            break
                if not merged:
                    st.session_state.cart.append({
                        "product_id":       prod_row["product_id"],
                        "product_name":     sel_name,
                        "sell_mode":        sell_mode,
                        "pricing_mode":     pricing_mode,
                        "unit_label":       unit_label,
                        "display_label":    display_label,
                        "quantity":         int(sel_qty),
                        "stock_deduct":     stock_deduct,
                        "unit_price":       default_price,
                        "negotiated_price": negotiated,
                        "cost_price":       cost_price_u,
                        "discount_pct":     0.0,
                        "discount_amt":     disc_amt,
                        "line_total":       line_total,
                        "cost_total":       cost_total,
                        "gross_profit":     gross_profit,
                    })
                st.session_state.sale_done = None
                st.rerun()

    # ── Cart display ──
    if not st.session_state.cart:
        st.info("Cart is empty. Add products above.")
    else:
        st.markdown("---")
        section_header("🧾 Cart Items")
        grand_total    = 0
        total_discount = 0
        total_cost     = 0
        total_profit   = 0

        for idx, item in enumerate(st.session_state.cart):
            ic1, ic2 = st.columns([6, 1])
            with ic1:
                neg = item.get("negotiated_price", item["unit_price"])
                if neg < item["unit_price"]:
                    price_str = (f"~~{fmt_naira(item['unit_price'])}~~ → "
                                 f"**{fmt_naira(neg)}** (-{fmt_naira(item['discount_amt'])})")
                elif neg > item["unit_price"]:
                    markup_amt = round((neg - item["unit_price"]) * item["quantity"], 2)
                    price_str = (f"~~{fmt_naira(item['unit_price'])}~~ → "
                                 f"**{fmt_naira(neg)}** (+{fmt_naira(markup_amt)})")
                else:
                    price_str = fmt_naira(item["unit_price"])
                st.markdown(
                    f"**{item['product_name']}** × {item['quantity']} "
                    f"{item.get('unit_label','unit')}s "
                    f"@ {price_str} — **{fmt_naira(item['line_total'])}**"
                )
            with ic2:
                if st.button("🗑️", key=f"rm_{idx}", help="Remove"):
                    st.session_state.cart.pop(idx)
                    st.rerun()
            grand_total    += item["line_total"]
            total_discount += item["discount_amt"]
            total_cost     += item["cost_total"]
            total_profit   += item["gross_profit"]
            if idx < len(st.session_state.cart) - 1:
                st.divider()

        st.markdown(f"""
<div class="kpi-card">
  <div class="kpi-label">Cart Summary</div>
  <div style="display:flex;gap:2rem;flex-wrap:wrap;margin-top:0.75rem;">
    <div><div class="kpi-label">Items</div>
     <div style="font-weight:700;font-size:1.1rem;color:#f1f5f9">{len(st.session_state.cart)}</div></div>
    <div><div class="kpi-label">Discount Given</div>
     <div style="font-weight:700;font-size:1.1rem;color:#ef4444">{fmt_naira(total_discount)}</div></div>
    <div><div class="kpi-label">Grand Total</div>
     <div style="font-weight:700;font-size:1.4rem;color:#00C896">{fmt_naira(grand_total)}</div></div>
    <div><div class="kpi-label">Gross Profit</div>
     <div style="font-weight:700;font-size:1.1rem;color:#6366f1">{fmt_naira(total_profit)}</div></div>
  </div>
</div>
        """, unsafe_allow_html=True)


def page_record_sale():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("🛒 Record a Sale", "Build a cart, apply discounts, print receipt")

    if "cart"      not in st.session_state: st.session_state.cart      = []
    if "sale_done" not in st.session_state: st.session_state.sale_done = None

    col1, col2 = st.columns([3, 2], gap="large")

    # ── LEFT: Build cart ──
    with col1:
        _build_cart_fragment(business_id)

    # ── RIGHT: Checkout + receipt ──
    with col2:
        section_header("💳 Checkout")

        if st.session_state.cart:
            # ── Payment status lives OUTSIDE the form so it re-renders reactively ──
            grand_total_preview = sum(i["line_total"] for i in st.session_state.cart)

            if "checkout_pay_status" not in st.session_state:
                st.session_state.checkout_pay_status = "full"

            payment_status = st.radio(
                "👇Select how customer is paying for the product",
                options=["full", "part", "credit"],
                format_func=lambda x: {
                    "full":   "✅ Full Payment",
                    "part":   "💳 Part Payment",
                    "credit": "📕 Credit (Owes Full Amount)",
                }[x],
                horizontal=True,
                key="checkout_pay_status",
                help="Select whether the customer paid in full, partially, or owes the full amount.",
            )

            # Amount paid input — only shown for part payment, also outside the form
            if payment_status == "part":
                amount_paid_now = st.number_input(
                    "Amount Paid Now (" + st.session_state.get("currency_symbol","₦") + ")",
                    min_value=0.0,
                    max_value=float(grand_total_preview),
                    value=0.0,
                    step=100.0,
                    key="checkout_amount_paid",
                    help="Enter how much the customer is paying now. The rest becomes a debt.",
                )
            elif payment_status == "credit":
                amount_paid_now = 0.0
                st.info("📕 The full amount will be recorded as a debt for this customer.")
            else:
                amount_paid_now = grand_total_preview
            
            st.markdown("---")

            # ── Customer picker lives OUTSIDE the form so choosing an
            # existing customer reactively fills their phone in below,
            # same reactivity pattern as payment_status above ──
            NEW_CUSTOMER_LABEL = "👤 select or type customer name"
            customer_directory = get_customer_directory(business_id)
            customer_options   = [NEW_CUSTOMER_LABEL] + [c["name"] for c in customer_directory]

            picked_customer = st.selectbox(
                "👨‍👩‍👧‍👧 Customer: Select From your Existing Customers",
                options=customer_options,
                key="checkout_customer_pick",
            )
            #st.caption("Type to search an existing customer, or pick 'New / walk-in customer' to add one.")

            if picked_customer == NEW_CUSTOMER_LABEL:
                customer_name  = st.text_input("Customer Name (optional)", placeholder="e.g. Obi Tayo",
                                                key="checkout_new_customer_name")
                customer_phone = st.text_input("Customer Phone (optional)", placeholder="e.g. +2348012345678",
                                                key="checkout_new_customer_phone")
            else:
                _matched = next((c for c in customer_directory if c["name"] == picked_customer), None)
                customer_name  = picked_customer
                customer_phone = st.text_input(
                    "Customer Phone (optional)",
                    value=(_matched["phone"] if _matched else ""),
                    key=f"checkout_existing_customer_phone_{picked_customer}",
                )
                st.caption("Auto-filled from their last sale — edit if it's changed.")

            with st.form("checkout_form"):
                payment_method = st.selectbox("Payment Method",
                                              ["Cash","Bank Transfer","POS","Mobile Money"])
                sale_note      = st.text_input("Note (optional)", placeholder="e.g. Bulk order")
                total_display  = fmt_naira(grand_total_preview)
                confirm_sale   = st.form_submit_button(
                    f"✅ Record Sale — {total_display}",
                    type="primary", width='stretch',
                )

            if confirm_sale:
                sale_id    = gen_id("SL")
                sale_time  = datetime.now().isoformat()
                cart       = st.session_state.cart
                grand_total    = sum(i["line_total"]   for i in cart)
                total_discount = sum(i["discount_amt"] for i in cart)
                total_cost     = sum(i["cost_total"]   for i in cart)
                total_profit   = sum(i["gross_profit"] for i in cart)
                # payment_status and amount_paid_now are set above outside the form
                _pay_status = st.session_state.get("checkout_pay_status", "full")
                _paid_now   = st.session_state.get("checkout_amount_paid", grand_total) \
                              if _pay_status == "part" else \
                              (0.0 if _pay_status == "credit" else grand_total)
                _cust_phone = customer_phone.strip()

                sale_ok = db_insert(TBL_SALES, {
                    "sale_id":        sale_id,
                    "business_id":    business_id,
                    "product_id":     cart[0]["product_id"],
                    "product_name":   ", ".join(i["product_name"] for i in cart),
                    "quantity":       sum(i["quantity"] for i in cart),
                    "unit_price":     cart[0]["unit_price"],
                    "total_amount":   grand_total,
                    "amount_paid":    round(_paid_now, 2),
                    "payment_status": _pay_status,
                    "cost_total":     total_cost,
                    "gross_profit":   total_profit,
                    "payment_method": payment_method,
                    "sale_date":      sale_time,
                    "customer_name":  customer_name.strip(),
                    "discount_total": total_discount,
                    "item_count":     len(cart),
                })

                if sale_ok:
                    # Bulk-insert all cart lines in one request instead of
                    # looping db_insert() per item (was N round-trips + N
                    # cache invalidations for an N-item cart).
                    db_insert_many(TBL_SALE_ITEMS, [
                        {
                            "item_id":      gen_id("ITM"),
                            "sale_id":      sale_id,
                            "business_id":  business_id,
                            "product_id":   item["product_id"],
                            "product_name": item["product_name"],
                            "quantity":     item["quantity"],
                            "unit_price":   item["unit_price"],
                            "discount_pct": item["discount_pct"],
                            "discount_amt": item["discount_amt"],
                            "line_total":   item["line_total"],
                            "cost_total":   item["cost_total"],
                            "gross_profit": item["gross_profit"],
                            # Stock was deducted in BASE units (may be fractional,
                            # e.g. 0.5 of a 12-pack bag). We must persist this so a
                            # future void restores the exact same base-unit amount
                            # instead of guessing from the sold quantity (which is
                            # in whatever unit — base or sub — the sale was made in).
                            "stock_deduct": item["stock_deduct"],
                            "sell_mode":    item["sell_mode"],
                        }
                        for item in cart
                    ])
                    # Deduct stock — business_id filter satisfies RLS.
                    # stock_quantity is float8 in Supabase to support sub-unit sales
                    # (e.g. selling 3 out of a 12-unit bag deducts 0.25 bags).
                    # ── Pre-commit stock guard (concurrent-use safety) ──────
                    # Fetch live stock for just the cart's products (not the
                    # whole catalogue) at commit time and validate every cart
                    # item before writing anything. If another device sold the
                    # same product between cart-build and checkout, we catch it
                    # here and abort cleanly instead of writing negative stock.
                    live_products = get_products_by_ids(
                        business_id, [item["product_id"] for item in cart]
                    )
                    stock_conflicts = []
                    if not live_products.empty:
                        for item in cart:
                            pr = live_products[
                                live_products["product_id"] == item["product_id"]
                            ]
                            if not pr.empty:
                                current = safe_float(pr.iloc[0]["stock_quantity"])
                                deduct  = safe_float(item.get("stock_deduct", item["quantity"]))
                                if deduct > current:
                                    upp_chk = safe_int(pr.iloc[0].get("units_per_pack", 1)) or 1
                                    avail_display = current * upp_chk if item.get("sell_mode") == "sub" else current
                                    unit_lbl = item.get("unit_label", "unit")
                                    stock_conflicts.append(
                                        f"**{item['product_name']}** — only "
                                        f"{avail_display:.0f} {unit_lbl}(s) left "
                                        f"(another sale may have just gone through)"
                                    )

                    if stock_conflicts:
                        st.error(
                            "⚠️ **Stock conflict — sale not saved.**\n\n"
                            "The following items no longer have enough stock:\n\n"
                            + "\n".join(f"• {c}" for c in stock_conflicts)
                            + "\n\nPlease remove or reduce those items and try again."
                        )
                    else:
                        # clear_cache=False on each write here — one write per
                        # cart item is unavoidable (each needs a different new
                        # stock value), but we only need to invalidate the
                        # products cache once, after the loop, not N times.
                        for item in cart:
                            if not live_products.empty:
                                pr = live_products[
                                    live_products["product_id"] == item["product_id"]
                                ]
                                if not pr.empty:
                                    current   = safe_float(pr.iloc[0]["stock_quantity"])
                                    deduct    = safe_float(item.get("stock_deduct", item["quantity"]))
                                    raw       = current - deduct
                                    # Keep fractional stock for sub-unit products (upp > 1),
                                    # whole numbers only for products sold in full packs only.
                                    upp       = safe_int(pr.iloc[0].get("units_per_pack", 1)) or 1
                                    if upp > 1:
                                        new_stock = round(max(0.0, raw), 4)  # float, e.g. 9.75 bags
                                    else:
                                        new_stock = int(max(0, round(raw)))  # integer, e.g. 7 units
                                    db_update(TBL_PRODUCTS, "product_id", item["product_id"],
                                              {"stock_quantity": new_stock}, clear_cache=False)
                        clear_table_cache(TBL_PRODUCTS)

                    # ── Debt recording (part payment or full credit) ──
                    _balance = round(grand_total - _paid_now, 2)
                    if _pay_status in ("part", "credit") and _balance > 0:
                        db_insert(TBL_DEBTS, {
                            "debt_id":       gen_id("DBT"),
                            "business_id":   business_id,
                            "sale_id":       sale_id,
                            "customer_name": customer_name.strip(),
                            "customer_phone": _cust_phone,
                            "total_amount":  grand_total,
                            "amount_paid":   round(_paid_now, 2),
                            "balance":       _balance,
                            "sale_date":     sale_time,
                            "status":        "partial" if _pay_status == "part" else "unpaid",
                            "note":          sale_note.strip(),
                        })

                    st.session_state.sale_done = {
                        "sale_id":       sale_id,
                        "sale_time":     sale_time,
                        "customer_name": customer_name.strip(),
                        "payment":       payment_method,
                        "payment_status": _pay_status,
                        "amount_paid_now": _paid_now,
                        "balance_owed":  round(grand_total - _paid_now, 2),
                        "note":          sale_note.strip(),
                        "items":         cart,
                        "grand_total":   grand_total,
                        "discount":      total_discount,
                        "profit":        total_profit,
                        "business_name": user.get("business_name", ""),
                    }
                    st.session_state.cart = []
                    # Reset checkout payment state for next sale
                    st.session_state.pop("checkout_pay_status", None)
                    st.session_state.pop("checkout_amount_paid", None)

                    # ── Cashbook mirror-write ────────────────────────────
                    # Only the amount actually collected today counts as cash in —
                    # a credit balance isn't cash until it's later collected via
                    # record_debt_payment(), which writes its own entry.
                    if _paid_now > 0:
                        log_cashbook_entry(
                            business_id=business_id, entry_date=sale_time,
                            entry_type="Sale", direction="In",
                            amount=_paid_now, payment_method=payment_method,
                            note=f"Sale to {customer_name.strip() or 'walk-in customer'}",
                            source_ref=sale_id,
                            recorded_by=user.get("full_name", user.get("email", "")),
                        )

                    # ── Activity logging ───────────────────────────────
                    _sub = user.get("plan_status", "active")
                    log_activity(business_id, "sale_recorded", _sub)
                    db_update(
                        "users", "business_id", business_id,
                        {"total_transactions": (user.get("total_transactions") or 0) + 1}
                    )
                    # ──────────────────────────────────────────────────

                    st.rerun()
                else:
                    st.error("Failed to record sale. Please try again.")

            if st.button("🗑️ Clear Cart", width='stretch'):
                st.session_state.cart      = []
                st.session_state.sale_done = None
                st.rerun()
        else:
            st.info("Add items to the cart to checkout.")

        # ── Receipt ──
        if st.session_state.get("sale_done"):
            rd = st.session_state.sale_done
            st.markdown("---")
            section_header("🧾 Receipt")

            _ps      = rd.get("payment_status", "full")
            _paid    = rd.get("amount_paid_now", rd["grand_total"])
            _balance = rd.get("balance_owed", 0)

            lines = [
                f"{'='*38}",
                f"  {rd['business_name'].upper()}",
                f"  {datetime.fromisoformat(rd['sale_time']).strftime('%d %b %Y  %H:%M')}",
                f"  Sale ID: {rd['sale_id']}",
            ]
            if rd["customer_name"]:
                lines.append(f"  Customer: {rd['customer_name']}")
            lines.append(f"{'='*38}")

            # Items
            for item in rd["items"]:
                neg  = item.get("negotiated_price", item["unit_price"])
                ulbl = item.get("unit_label", "unit")
                lines.append(f"  {item['product_name'][:22]:<22}")
                lines.append(f"  {item['quantity']} {ulbl}(s) x {fmt_naira(neg)} = {fmt_naira(item['line_total'])}")

            lines.append(f"{'='*38}")
            lines.append(f"  TOTAL:        {fmt_naira(rd['grand_total'])}")
            lines.append(f"  Payment:      {rd['payment']}")

            # Debt / part payment section
            if _ps == "part":
                lines.append(f"  {'-'*36}")
                lines.append(f"  💳 PART PAYMENT")
                lines.append(f"  Paid Today:   {fmt_naira(_paid)}")
                lines.append(f"  Balance Owed: {fmt_naira(_balance)}")
                lines.append(f"  {'-'*36}")
                lines.append(f"  Please settle the balance at your")
                lines.append(f"  earliest convenience.")
            elif _ps == "credit":
                lines.append(f"  {'-'*36}")
                lines.append(f"  📕 CREDIT SALE")
                lines.append(f"  Paid Today:   {fmt_naira(0)}")
                lines.append(f"  Balance Owed: {fmt_naira(rd['grand_total'])}")
                lines.append(f"  {'-'*36}")
                lines.append(f"  Full amount is owed.")

            if rd["note"]:
                lines.append(f"  Note: {rd['note']}")
            lines += [
                f"{'='*38}",
                "  Thank you for your purchase!",
                f"{'='*38}",
            ]
            st.code("\n".join(lines), language=None)

            # PDF Receipt
            try:
                from reportlab.lib.pagesizes import A6
                from reportlab.lib import colors
                from reportlab.lib.units import mm
                from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                                Spacer, HRFlowable, Table, TableStyle)
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                import os

                # ── Fonts ──────────────────────────────────────────────────────────
                _assets     = os.path.join(os.path.dirname(__file__), "..", "assets")
                _font_path  = os.path.join(_assets, "DejaVuSans.ttf")
                _fontb_path = os.path.join(_assets, "DejaVuSans-Bold.ttf")
                try:
                    pdfmetrics.registerFont(TTFont("DejaVuSans",      _font_path))
                    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold",  _fontb_path))
                    _body_font = "DejaVuSans"
                    _bold_font = "DejaVuSans-Bold"
                except Exception:
                    _body_font = "Helvetica"
                    _bold_font = "Helvetica-Bold"

                # ── Colors ─────────────────────────────────────────────────────────
                DARK_BG   = colors.HexColor("#0D1117")
                GOLD      = colors.HexColor("#F5A623")
                SLATE     = colors.HexColor("#8BA0B8")
                ROW_ALT   = colors.HexColor("#F7F9FB")
                RED_DARK  = colors.HexColor("#991B1B")
                RED_LIGHT = colors.HexColor("#FEF2F2")
                RED_BORD  = colors.HexColor("#FCA5A5")
                RULE      = colors.HexColor("#E2E8F0")
                INK       = colors.HexColor("#0F172A")

                # ── Page ───────────────────────────────────────────────────────────
                buf = io.BytesIO()
                doc = SimpleDocTemplate(
                    buf, pagesize=A6,
                    leftMargin=10*mm, rightMargin=10*mm,
                    topMargin=0*mm,   bottomMargin=8*mm,
                )
                styl = getSampleStyleSheet()

                def _p(name, font=_body_font, size=8, align=TA_CENTER,
                       color=INK, sa=1, leading=None):
                    return ParagraphStyle(
                        name, parent=styl["Normal"],
                        fontName=font, fontSize=size,
                        alignment=align, textColor=color,
                        spaceAfter=sa, leading=leading or size * 1.4,
                    )

                S_BIZ    = _p("biz",   _bold_font, 13, TA_CENTER, GOLD,     sa=2)
                S_META   = _p("meta",  _body_font,  8, TA_CENTER, SLATE,    sa=1)
                S_NC     = _p("nc",    _body_font,  8, TA_CENTER, INK,      sa=1)
                S_SMALL  = _p("small", _body_font,  7, TA_CENTER, SLATE,    sa=1)
                S_ID_L   = _p("idl",   _body_font,  7, TA_LEFT,   SLATE,    sa=0)
                S_ID_V   = _p("idv",   _bold_font,  7, TA_RIGHT,  INK,      sa=0)
                S_TH     = _p("th",    _bold_font,  8, TA_LEFT,   SLATE,    sa=0)
                S_TH_R   = _p("thr",   _bold_font,  8, TA_RIGHT,  SLATE,    sa=0)
                S_TD     = _p("td",    _body_font,  8, TA_LEFT,   INK,      sa=0)
                S_TD_R   = _p("tdr",   _body_font,  8, TA_RIGHT,  INK,      sa=0)
                S_LBL    = _p("lbl",   _body_font,  8, TA_LEFT,   SLATE,    sa=2)
                S_VAL    = _p("val",   _bold_font,  8, TA_RIGHT,  INK,      sa=2)
                S_TOTAL  = _p("tot",   _bold_font, 11, TA_CENTER, INK,      sa=2)
                S_DEBT_H = _p("dh",    _bold_font,  9, TA_CENTER, RED_DARK, sa=2)
                S_DEBT_B = _p("db",    _bold_font,  8, TA_CENTER, RED_DARK, sa=2)
                S_DEBT_N = _p("dn",    _body_font,  7, TA_CENTER, SLATE,    sa=1)
                S_THANKS = _p("thx",   _body_font,  8, TA_CENTER, SLATE,    sa=1)
                S_POWER  = _p("pwr",   _body_font,  7, TA_CENTER, SLATE,    sa=0)

                story = []

                # ── Dark header band ────────────────────────────────────────────────
                sale_dt = datetime.fromisoformat(rd["sale_time"]).strftime("%d %b %Y  ·  %H:%M")
                hdr_rows = [[Paragraph(rd["business_name"].upper(), S_BIZ)],
                             [Paragraph(sale_dt, S_META)]]
                if rd.get("customer_name"):
                    hdr_rows.append([Paragraph(f"Customer: {rd['customer_name']}", S_META)])
                hdr_tbl = Table(hdr_rows, colWidths=[86*mm])
                hdr_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), DARK_BG),
                    ("TOPPADDING",    (0,0), (-1, 0), 7),
                    ("BOTTOMPADDING", (0,-1),(-1,-1), 7),
                    ("TOPPADDING",    (0,1), (-1,-1), 1),
                    ("BOTTOMPADDING", (0,0), (-1,-2), 1),
                    ("LEFTPADDING",   (0,0), (-1,-1), 6),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 6),
                ]))
                story.append(hdr_tbl)

                # ── Currency symbol for this receipt ────────────────────────────────
                _cs = st.session_state.get("currency_symbol", "₦")

                # ── Sale ID row ─────────────────────────────────────────────────────
                id_tbl = Table(
                    [[Paragraph("Sale ID", S_ID_L), Paragraph(rd["sale_id"], S_ID_V)]],
                    colWidths=[43*mm, 43*mm],
                )
                id_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), ROW_ALT),
                    ("TOPPADDING",    (0,0), (-1,-1), 4),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                    ("LEFTPADDING",   (0,0), (-1,-1), 6),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 6),
                    ("LINEBELOW",     (0,0), (-1,-1), 0.5, RULE),
                ]))
                story.append(id_tbl)
                story.append(Spacer(1, 3*mm))

                # ── Items table ─────────────────────────────────────────────────────
                tdata = [[
                    Paragraph("Item",  S_TH),
                    Paragraph("Qty",   S_TH_R),
                    Paragraph("Price", S_TH_R),
                    Paragraph("Total", S_TH_R),
                ]]
                for item in rd["items"]:
                    neg = item.get("negotiated_price", item["unit_price"])
                    tdata.append([
                        Paragraph(item["product_name"][:20], S_TD),
                        Paragraph(str(item["quantity"]),     S_TD_R),
                        Paragraph(f"{_cs}{neg:,.0f}",           S_TD_R),
                        Paragraph(f"{_cs}{item['line_total']:,.0f}", S_TD_R),
                    ])
                items_tbl = Table(tdata, colWidths=[42*mm, 10*mm, 17*mm, 17*mm])
                items_tbl.setStyle(TableStyle([
                    ("FONTSIZE",       (0,0), (-1,-1), 8),
                    ("LINEBELOW",      (0,0), (-1, 0), 0.5, RULE),
                    ("LINEBELOW",      (0,1), (-1,-1), 0.3, RULE),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, ROW_ALT]),
                    ("TOPPADDING",     (0,0), (-1,-1), 4),
                    ("BOTTOMPADDING",  (0,0), (-1,-1), 4),
                    ("LEFTPADDING",    (0,0), (-1,-1), 0),
                    ("RIGHTPADDING",   (0,0), (-1,-1), 0),
                ]))
                story.append(items_tbl)
                story.append(Spacer(1, 3*mm))

                # ── Totals ──────────────────────────────────────────────────────────
                tot_rows = [[Paragraph("Payment method", S_LBL),
                              Paragraph(rd["payment"], S_VAL)]]
                if rd.get("discount", 0) > 0:
                    tot_rows.append([Paragraph("Discount", S_LBL),
                                     Paragraph(f"–{_cs}{rd['discount']:,.0f}", S_VAL)])
                tot_tbl = Table(tot_rows, colWidths=[50*mm, 36*mm])
                tot_tbl.setStyle(TableStyle([
                    ("TOPPADDING",    (0,0), (-1,-1), 3),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                    ("LEFTPADDING",   (0,0), (-1,-1), 0),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 0),
                ]))
                story.append(tot_tbl)
                story.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
                story.append(Spacer(1, 2*mm))
                story.append(Paragraph(f"Total  {_cs}{rd['grand_total']:,.0f}", S_TOTAL))
                story.append(Spacer(1, 3*mm))

                # ── Part payment / credit block ─────────────────────────────────────
                _ps_pdf   = rd.get("payment_status", "full")
                _paid_pdf = float(rd.get("amount_paid_now", rd["grand_total"]) or 0)
                _bal_pdf  = float(rd.get("balance_owed", 0) or 0)

                if _ps_pdf in ("part", "credit"):
                    if _ps_pdf == "part":
                        _label     = "PART PAYMENT"
                        _paid_line = f"Paid Today:   {_cs}{_paid_pdf:,.0f}"
                        _bal_line  = f"Balance Owed: {_cs}{_bal_pdf:,.0f}"
                    else:
                        _label     = "CREDIT SALE"
                        _paid_line = f"Paid Today:   {_cs}0"
                        _bal_line  = f"Balance Owed: {_cs}{rd['grand_total']:,.0f}"
                    _note_line = "Please settle the balance as soon as possible."

                    debt_rows = [
                        [Paragraph(_label,     S_DEBT_H)],
                        [Paragraph(_paid_line, S_DEBT_B)],
                        [Paragraph(_bal_line,  S_DEBT_B)],
                        [Paragraph(_note_line, S_DEBT_N)],
                    ]
                    debt_tbl = Table(debt_rows, colWidths=[86*mm])
                    debt_tbl.setStyle(TableStyle([
                        ("BACKGROUND",    (0,0), (-1,-1), RED_LIGHT),
                        ("BOX",           (0,0), (-1,-1), 0.5, RED_BORD),
                        ("LINEBELOW",     (0,2), (-1, 2), 0.5, RED_BORD),
                        ("TOPPADDING",    (0,0), (-1, 0), 6),
                        ("BOTTOMPADDING", (0,-1),(-1,-1), 6),
                        ("TOPPADDING",    (0,1), (-1,-1), 2),
                        ("BOTTOMPADDING", (0,0), (-1,-2), 2),
                        ("LEFTPADDING",   (0,0), (-1,-1), 6),
                        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
                    ]))
                    story.append(debt_tbl)
                    story.append(Spacer(1, 3*mm))

                # ── Note ────────────────────────────────────────────────────────────
                _note = rd.get("note") or ""
                if _note.strip():
                    story.append(Paragraph(f"Note: {_note}", S_SMALL))
                    story.append(Spacer(1, 2*mm))

                # ── Footer ──────────────────────────────────────────────────────────
                story.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
                story.append(Spacer(1, 2*mm))
                story.append(Paragraph("Thank you for your purchase!", S_THANKS))
                story.append(Paragraph("Powered by BizTrack-OS", S_POWER))

                doc.build(story)
                pdf_bytes = buf.getvalue()
                fname = (f"receipt_{rd['sale_id']}_"
                         f"{datetime.fromisoformat(rd['sale_time']).strftime('%Y%m%d_%H%M')}.pdf")
                st.download_button("📄 Download PDF Receipt", data=pdf_bytes,
                                   file_name=fname, mime="application/pdf",
                                   width='stretch', type="primary")

                item_lines = ", ".join(
                    f"{i['product_name']} x{i['quantity']}" for i in rd["items"]
                )
                _wa_ps   = rd.get("payment_status", "full")
                _wa_paid = rd.get("amount_paid_now", rd["grand_total"])
                _wa_bal  = rd.get("balance_owed", 0)

                _wa_cs  = st.session_state.get("currency_symbol", "₦")
                wa_text = (
                    f"Receipt from {rd['business_name']}\n"
                    f"Date: {datetime.fromisoformat(rd['sale_time']).strftime('%d %b %Y %H:%M')}\n"
                    f"Items: {item_lines}\n"
                    f"Total: {_wa_cs}{rd['grand_total']:,.0f}\n"
                    f"Payment: {rd['payment']}\n"
                )
                if _wa_ps == "part":
                    wa_text += (
                        f"--- PART PAYMENT ---\n"
                        f"Paid Today: {_wa_cs}{_wa_paid:,.0f}\n"
                        f"Balance Owed: {_wa_cs}{_wa_bal:,.0f}\n"
                        f"Please settle the balance as soon as possible.\n"
                    )
                elif _wa_ps == "credit":
                    wa_text += (
                        f"--- CREDIT SALE ---\n"
                        f"Balance Owed: {_wa_cs}{rd['grand_total']:,.0f}\n"
                        f"Full amount is owed. Please settle the balance as soon as possible.\n"
                    )
                wa_text += "Thank you!"
                wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"
                st.markdown(
                    f"""<a href="{wa_url}" target="_blank"
                        style="display:block;text-align:center;background:#25D366;
                               color:white;padding:0.6rem;border-radius:8px;
                               font-weight:600;text-decoration:none;margin-top:0.5rem;">
                        💬 Share via WhatsApp</a>""",
                    unsafe_allow_html=True,
                )
            except ImportError:
                st.warning("Install reportlab for PDF receipts: pip install reportlab")
            except Exception as _pdf_err:
                st.error(f"PDF receipt error: {_pdf_err}")

    # ── Today's Sales ──
    st.markdown("---")
    section_header("Today's Sales")
    today       = datetime.now().date()
    sales_df    = get_sales_df(business_id)
    # Also refresh products so low-stock alerts are accurate
    products_df = get_products_df_live(business_id)
    today_sales = (sales_df[sales_df["sale_date"].dt.date == today]
                   if not sales_df.empty else pd.DataFrame())
    kpi_card("Today's Revenue",
             fmt_naira(today_sales["total_amount"].sum() if not today_sales.empty else 0),
             f"{len(today_sales)} transactions today", icon="💰")
    if not today_sales.empty:
        st.markdown("**Recent transactions:**")
        for _, r in today_sales.sort_values("sale_date", ascending=False).head(5).iterrows():
            st.markdown(f"• **{r['product_name']}** = {fmt_naira(r['total_amount'])} _{r['payment_method']}_")


# ══════════════════════════════════════════════════════════════════════════════
# SALES HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def page_sales_history():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📋 Sales History", "View, edit or void past transactions")

    if st.session_state.get("sale_feedback"):
        msg = st.session_state.pop("sale_feedback")
        (st.success if msg.startswith("✅") else st.error)(msg)

    sales_df = get_sales_df(business_id)
    if sales_df.empty:
        st.info("📭 No sales recorded yet.")
        return

    # Load all sale items once — filtered per-row inside the loop (no N+1 queries)
    all_items_df = get_sale_items_df(business_id)

    # ── Filters ──
    col1, col2, col3 = st.columns(3)
    start_date = col1.date_input("From", value=(datetime.now() - timedelta(days=30)).date())
    end_date   = col2.date_input("To",   value=datetime.now().date())
    search_q   = col3.text_input("🔍 Search", placeholder="Product or customer name…")

    filtered = sales_df[
        (sales_df["sale_date"].dt.date >= start_date) &
        (sales_df["sale_date"].dt.date <= end_date)
    ]
    if search_q:
        filtered = filtered[
            filtered["product_name"].str.contains(search_q, case=False, na=False) |
            filtered["customer_name"].str.contains(search_q, case=False, na=False)
        ]
    filtered = filtered.sort_values("sale_date", ascending=False)

    # ── Period KPIs ──
    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Total Revenue",  fmt_naira(filtered["total_amount"].sum()), f"{len(filtered)} transactions", icon="💰")
    with c2: kpi_card("Total Profit",   fmt_naira(filtered["gross_profit"].sum()),  "Gross profit",                 icon="📈")
    with c3: kpi_card("Avg Sale Value", fmt_naira(filtered["total_amount"].mean() if not filtered.empty else 0), "Per transaction", icon="📊")
    with c4:
        disc = filtered["discount_total"].sum() if "discount_total" in filtered.columns else 0
        kpi_card("Total Discounts", fmt_naira(disc), "Given in period", positive=(disc == 0), icon="🏷️")

    st.markdown("---")

    # ── Pagination ──
    PAGE_SIZE   = 20
    total_pages = max(1, -(-len(filtered) // PAGE_SIZE))
    if "sales_hist_page" not in st.session_state:
        st.session_state.sales_hist_page = 1
    pg       = st.session_state.sales_hist_page
    page_df  = filtered.iloc[(pg-1)*PAGE_SIZE: pg*PAGE_SIZE]
    st.caption(f"Showing {len(page_df)} of {len(filtered)} records  •  Page {pg} of {total_pages}")

    for _, r in page_df.iterrows():
        sale_id = r["sale_id"]
        with st.expander(
            f"**{r['product_name'][:40]}** | {fmt_naira(r['total_amount'])} | "
            f"{r['payment_method']} | {r['sale_date'].strftime('%d %b %Y %H:%M') if pd.notna(r['sale_date']) else ''}",
            expanded=False,
        ):
            dc1, dc2 = st.columns(2)
            dc1.markdown(f"**Sale ID:** `{sale_id}`")
            dc1.markdown(f"**Customer:** {r.get('customer_name','—') or '—'}")
            dc2.markdown(f"**Gross Profit:** {fmt_naira(r['gross_profit'])}")
            dc2.markdown(f"**Items:** {int(r.get('item_count', 1))}")

            # ── Line-item breakdown ──────────────────────────────────
            row_items = all_items_df[all_items_df["sale_id"] == sale_id] \
                if not all_items_df.empty else pd.DataFrame()
            if not row_items.empty:
                with st.expander("🧾 View Items", expanded=False):
                    for _, it in row_items.iterrows():
                        disc_note = (
                            f"  *(disc: {fmt_naira(it['discount_amt'])})*"
                            if it.get("discount_amt") else ""
                        )
                        st.markdown(
                            f"• **{it['product_name']}** × {it['quantity']}  "
                            f"@ {fmt_naira(it['unit_price'])}  → **{fmt_naira(it['line_total'])}**"
                            + disc_note
                        )

            with st.form(f"edit_sale_{sale_id}"):
                ef1, ef2 = st.columns(2)
                new_pm   = ef1.selectbox("Payment Method",
                                         ["Cash","Bank Transfer","POS","Mobile Money"],
                                         index=["Cash","Bank Transfer","POS","Mobile Money"].index(r["payment_method"])
                                         if r["payment_method"] in ["Cash","Bank Transfer","POS","Mobile Money"] else 0)
                new_amt  = ef2.number_input("Total Amount (" + st.session_state.get("currency_symbol","₦") + ")", value=safe_float(r["total_amount"]),
                                             min_value=0.0, step=100.0)
                save = st.form_submit_button("💾 Save Changes", type="primary")

            if save:
                ok = db_update(TBL_SALES, "sale_id", sale_id,
                               {"payment_method": new_pm, "total_amount": new_amt})
                st.session_state.sale_feedback = (
                    "✅ Sale updated." if ok else "❌ Update failed."
                )
                st.rerun()

            # ── PIN-protected void ──────────────────────────────────────
            void_key    = f"void_{sale_id}"
            pin_err_key = f"pin_err_{sale_id}"
            user        = st.session_state.get("user", {})

            if not st.session_state.get(void_key, False):
                if st.button("🗑️ Void Sale", key=f"del_sale_{sale_id}",
                             help="Void this sale and restore stock"):
                    st.session_state[void_key]    = True
                    st.session_state[pin_err_key] = ""
                    st.rerun()
            else:
                st.warning("⚠️ Void this sale? Stock will be restored.")

                if not has_void_pin(user):
                    # No PIN set — warn owner and still allow void so they
                    # are not locked out, but nudge them to set a PIN.
                    st.info(
                        "ℹ️ No Void PIN is set. Go to **⚙️ Settings** to add one "
                        "and protect sales records from unauthorised deletion."
                    )
                    vc1, vc2 = st.columns(2)
                    if vc1.button("✅ Yes, void", key=f"yes_void_{sale_id}", type="primary"):
                        items_df = db_fetch(TBL_SALE_ITEMS,
                                            {"sale_id": sale_id, "business_id": business_id})
                        live     = get_products_df(business_id)
                        if not items_df.empty and not live.empty:
                            for _, item in items_df.iterrows():
                                pr = live[live["product_id"] == item["product_id"]]
                                if not pr.empty:
                                    restored = _restore_stock_amount(pr.iloc[0], item)
                                    db_update(TBL_PRODUCTS, "product_id", item["product_id"],
                                              {"stock_quantity": restored}, clear_cache=False)
                            clear_table_cache(TBL_PRODUCTS)
                        ok = db_delete(TBL_SALES, "sale_id", sale_id)
                        if not items_df.empty:
                            db_delete(TBL_SALE_ITEMS, "sale_id", sale_id)
                        db_delete(TBL_CASHBOOK, "source_ref", sale_id)
                        st.session_state.pop(void_key, None)
                        st.session_state.pop(pin_err_key, None)
                        st.session_state.sale_feedback = (
                            "✅ Sale voided and stock restored." if ok else "❌ Failed to void."
                        )
                        st.rerun()
                    if vc2.button("❌ Cancel", key=f"no_void_{sale_id}"):
                        st.session_state.pop(void_key, None)
                        st.session_state.pop(pin_err_key, None)
                        st.rerun()

                else:
                    # PIN is set — require it before proceeding
                    if st.session_state.get(pin_err_key):
                        st.error(st.session_state[pin_err_key])

                    with st.form(f"void_pin_form_{sale_id}", clear_on_submit=True):
                        entered_pin = st.text_input(
                            "🔐 Enter Void PIN to confirm",
                            type="password",
                            placeholder="Your manager PIN",
                        )
                        pf1, pf2 = st.columns(2)
                        confirm_void = pf1.form_submit_button("✅ Confirm Void", type="primary")
                        cancel_void  = pf2.form_submit_button("❌ Cancel")

                    if confirm_void:
                        if verify_void_pin(user, entered_pin):
                            items_df = db_fetch(TBL_SALE_ITEMS,
                                                {"sale_id": sale_id, "business_id": business_id})
                            live     = get_products_df(business_id)
                            if not items_df.empty and not live.empty:
                                for _, item in items_df.iterrows():
                                    pr = live[live["product_id"] == item["product_id"]]
                                    if not pr.empty:
                                        restored = _restore_stock_amount(pr.iloc[0], item)
                                        db_update(TBL_PRODUCTS, "product_id", item["product_id"],
                                                  {"stock_quantity": restored}, clear_cache=False)
                                clear_table_cache(TBL_PRODUCTS)
                            ok = db_delete(TBL_SALES, "sale_id", sale_id)
                            if not items_df.empty:
                                db_delete(TBL_SALE_ITEMS, "sale_id", sale_id)
                            db_delete(TBL_CASHBOOK, "source_ref", sale_id)
                            st.session_state.pop(void_key, None)
                            st.session_state.pop(pin_err_key, None)
                            st.session_state.sale_feedback = (
                                "✅ Sale voided and stock restored." if ok else "❌ Failed to void."
                            )
                            st.rerun()
                        else:
                            st.session_state[pin_err_key] = "❌ Incorrect PIN. Sale not voided."
                            st.rerun()

                    if cancel_void:
                        st.session_state.pop(void_key, None)
                        st.session_state.pop(pin_err_key, None)
                        st.rerun()

    if total_pages > 1:
        st.markdown("---")
        pc1, pc2, pc3 = st.columns([1, 3, 1])
        if pc1.button("◀ Prev", disabled=(pg <= 1), key="sh_prev"):
            st.session_state.sales_hist_page = max(1, pg-1); st.rerun()
        pc2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {pg} of {total_pages}</div>",
                     unsafe_allow_html=True)
        if pc3.button("Next ▶", disabled=(pg >= total_pages), key="sh_next"):
            st.session_state.sales_hist_page = min(total_pages, pg+1); st.rerun()
