# ============================================================
#  pages/page_sales_history.py
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


def page_sales_history():
    """Sales History page: date filter, edit, delete with inventory reconciliation."""
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📋 Sales History", "View, edit or void past transactions")

    # Force fresh fetch if a sale was just edited/voided
    if st.session_state.get("sale_feedback"):
        st.cache_data.clear()

    sales_df = get_sales_df(business_id)
    if sales_df.empty:
        st.info("📭 No sales recorded yet.")
        return

    products_df = get_products_df(business_id)

    # ── Filters ──
    fc1, fc2, fc3 = st.columns(3)
    start_date  = fc1.date_input("From", value=(datetime.now() - timedelta(days=30)).date(), key="sh_from")
    end_date    = fc2.date_input("To",   value=datetime.now().date(), key="sh_to")
    search_sale = fc3.text_input("🔍 Search product", key="sh_search", placeholder="Product name…")

    # Safely parse sale_date — drop any rows where it couldn't be parsed
    sales_df = sales_df.dropna(subset=["sale_date"])
    sales_df["sale_date"] = pd.to_datetime(sales_df["sale_date"], errors="coerce", utc=True).dt.tz_localize(None)
    sales_df = sales_df.dropna(subset=["sale_date"])

    filtered = sales_df[
        (sales_df["sale_date"].dt.date >= start_date) &
        (sales_df["sale_date"].dt.date <= end_date)
    ]
    if search_sale:
        filtered = filtered[filtered["product_name"].str.contains(search_sale, case=False, na=False)]

    filtered = filtered.sort_values("sale_date", ascending=False)

    # ── Summary KPIs ──
    sk1, sk2, sk3 = st.columns(3)
    with sk1:
        kpi_card("Revenue (filtered)", fmt_naira(filtered["total_amount"].sum()), f"{len(filtered)} transactions")
    with sk2:
        kpi_card("Profit (filtered)", fmt_naira(filtered["gross_profit"].sum()), "Gross margin")
    with sk3:
        kpi_card("Avg Sale Value", fmt_naira(filtered["total_amount"].mean() if not filtered.empty else 0), "Per transaction")

    st.markdown("---")

    if filtered.empty:
        st.info("No sales match the current filters.")
        return

    # ── Pagination ──
    SH_PAGE_SIZE = 15
    sh_total_pages = max(1, -(-len(filtered) // SH_PAGE_SIZE))
    if "sh_page" not in st.session_state:
        st.session_state.sh_page = 1
    sh_pg = st.session_state.sh_page
    page_df = filtered.iloc[(sh_pg - 1) * SH_PAGE_SIZE: sh_pg * SH_PAGE_SIZE]
    st.caption(f"Showing {len(page_df)} of {len(filtered)} sales  •  Page {sh_pg} of {sh_total_pages}")

    # ── Global feedback banner (outside expanders) ──
    if "sale_feedback" in st.session_state:
        msg = st.session_state.pop("sale_feedback")
        if msg.startswith("✅"):
            st.success(msg)
        else:
            st.error(msg)

    # ── Sale rows ──
    for _, r in page_df.iterrows():
        sale_id  = r["sale_id"]
        sale_dt  = r["sale_date"].strftime("%d %b %Y %H:%M") if pd.notna(r["sale_date"]) else "—"
        # Keep expander open if this sale was just edited
        is_expanded = st.session_state.get("last_edited_sale") == sale_id
        with st.expander(
            f"**{r['product_name']}** × {int(r['quantity'])}  |  "
            f"{fmt_naira(r['total_amount'])}  |  {r['payment_method']}  |  {sale_dt}",
            expanded=is_expanded
        ):
            # ── Edit form ──
            with st.form(f"edit_sale_{sale_id}"):
                sf1, sf2 = st.columns(2)

                # Product selector
                prod_names = products_df["product_name"].tolist() if not products_df.empty else [r["product_name"]]
                try:
                    prod_idx = prod_names.index(r["product_name"])
                except ValueError:
                    prod_idx = 0
                new_product_name = sf1.selectbox("Product", prod_names, index=prod_idx)
                new_payment      = sf2.selectbox(
                    "Payment Method",
                    ["Cash", "Bank Transfer", "POS", "Mobile Money"],
                    index=["Cash","Bank Transfer","POS","Mobile Money"].index(r["payment_method"])
                    if r["payment_method"] in ["Cash","Bank Transfer","POS","Mobile Money"] else 0
                )
                new_qty  = sf1.number_input("Quantity", min_value=1, value=int(r["quantity"]), step=1)
                new_date = sf2.date_input(
                    "Sale Date",
                    value=r["sale_date"].date() if pd.notna(r["sale_date"]) else datetime.now().date()
                )
                save_sale = st.form_submit_button("💾 Save Changes", type="primary")

            if save_sale:
                # Resolve new product details
                if not products_df.empty:
                    prod_row = products_df[products_df["product_name"] == new_product_name]
                    if not prod_row.empty:
                        new_unit_price = safe_float(prod_row.iloc[0]["selling_price"])
                        new_cost_price = safe_float(prod_row.iloc[0]["cost_price"])
                        new_product_id = prod_row.iloc[0]["product_id"]
                    else:
                        new_unit_price = safe_float(r["unit_price"])
                        new_cost_price = new_unit_price
                        new_product_id = r.get("product_id", "")
                else:
                    new_unit_price = safe_float(r["unit_price"])
                    new_cost_price = new_unit_price
                    new_product_id = r.get("product_id", "")

                old_qty        = int(r["quantity"])
                old_product_id = r.get("product_id", "")
                product_changed = (new_product_id != old_product_id)

                new_total  = new_unit_price * new_qty
                new_cost_t = new_cost_price * new_qty
                new_profit = new_total - new_cost_t

                # ── Fetch LIVE stock before any check or update ──
                live_products = get_products_df(business_id)

                # If product changed: fully restore old product stock, fully deduct new
                if product_changed:
                    # Check new product has enough stock
                    if not live_products.empty:
                        new_prod_live = live_products[live_products["product_id"] == new_product_id]
                        if not new_prod_live.empty:
                            avail = int(new_prod_live.iloc[0]["stock_quantity"])
                            if new_qty > avail:
                                st.error(f"Not enough stock for {new_product_name}. Only {avail} units available.")
                                st.stop()
                else:
                    # Same product — only check the extra qty needed
                    qty_delta = new_qty - old_qty
                    if qty_delta > 0 and not live_products.empty:
                        same_prod_live = live_products[live_products["product_id"] == new_product_id]
                        if not same_prod_live.empty:
                            avail = int(same_prod_live.iloc[0]["stock_quantity"])
                            if qty_delta > avail:
                                st.error(f"Not enough stock. Only {avail} extra units available.")
                                st.stop()

                # ── Update the sale record ──
                ok = db_update(TBL_SALES, "sale_id", sale_id, {
                    "product_id":     new_product_id,
                    "product_name":   new_product_name,
                    "quantity":       new_qty,
                    "unit_price":     new_unit_price,
                    "total_amount":   new_total,
                    "cost_total":     new_cost_t,
                    "gross_profit":   new_profit,
                    "payment_method": new_payment,
                    "sale_date":      datetime.combine(new_date, datetime.now().time()).isoformat(),
                })

                if ok:
                    # ── Reconcile stock using LIVE values ──
                    if not live_products.empty:
                        if product_changed:
                            # Restore full old_qty to old product
                            old_prod_live = live_products[live_products["product_id"] == old_product_id]
                            if not old_prod_live.empty:
                                restored = int(old_prod_live.iloc[0]["stock_quantity"]) + old_qty
                                db_update(TBL_PRODUCTS, "product_id", old_product_id, {"stock_quantity": restored})
                            # Deduct full new_qty from new product
                            new_prod_live = live_products[live_products["product_id"] == new_product_id]
                            if not new_prod_live.empty:
                                deducted = int(new_prod_live.iloc[0]["stock_quantity"]) - new_qty
                                db_update(TBL_PRODUCTS, "product_id", new_product_id, {"stock_quantity": max(0, deducted)})
                        else:
                            # Same product — apply qty delta only
                            qty_delta = new_qty - old_qty
                            same_prod_live = live_products[live_products["product_id"] == new_product_id]
                            if not same_prod_live.empty:
                                adjusted = int(same_prod_live.iloc[0]["stock_quantity"]) - qty_delta
                                db_update(TBL_PRODUCTS, "product_id", new_product_id, {"stock_quantity": max(0, adjusted)})

                    st.cache_data.clear()
                    st.session_state["sale_feedback"]   = "✅ Sale updated and inventory reconciled."
                    st.session_state["last_edited_sale"] = sale_id
                    st.rerun()
                else:
                    st.session_state["sale_feedback"]   = "❌ Failed to update sale. Please try again."
                    st.session_state["last_edited_sale"] = sale_id
                    st.rerun()

            # ── Delete / Void ──
            confirm_void_key = f"confirm_void_{sale_id}"
            if not st.session_state.get(confirm_void_key, False):
                if st.button("🗑️ Void / Delete this sale", key=f"void_{sale_id}"):
                    st.session_state[confirm_void_key] = True
                    st.rerun()
            else:
                st.warning(
                    f"⚠️ Void **{r['product_name']} × {int(r['quantity'])}** "
                    f"({fmt_naira(r['total_amount'])})? "
                    f"This will restore {int(r['quantity'])} units to stock."
                )
                vd1, vd2 = st.columns(2)
                if vd1.button("✅ Yes, void sale", key=f"yes_void_{sale_id}", type="primary"):
                    ok = db_delete(TBL_SALES, "sale_id", sale_id)
                    if ok:
                        # Fetch LIVE stock before restoring
                        live_products = get_products_df(business_id)
                        if not live_products.empty:
                            prod_live = live_products[live_products["product_id"] == r.get("product_id", "")]
                            if prod_live.empty:
                                # fallback: match by name
                                prod_live = live_products[live_products["product_name"] == r["product_name"]]
                            if not prod_live.empty:
                                restored = int(prod_live.iloc[0]["stock_quantity"]) + int(r["quantity"])
                                db_update(TBL_PRODUCTS, "product_id", prod_live.iloc[0]["product_id"], {"stock_quantity": restored})
                        st.cache_data.clear()
                        st.session_state.pop(confirm_void_key, None)
                        st.session_state["sale_feedback"] = f"✅ Sale voided. {int(r['quantity'])} units restored to stock."
                        st.rerun()
                    else:
                        st.session_state["sale_feedback"] = "❌ Failed to void sale. Please try again."
                        st.rerun()
                if vd2.button("❌ Cancel", key=f"no_void_{sale_id}"):
                    st.session_state.pop(confirm_void_key, None)
                    st.rerun()

    # ── Pagination controls ──
    if sh_total_pages > 1:
        st.markdown("---")
        pp1, pp2, pp3 = st.columns([1, 3, 1])
        if pp1.button("◀ Prev", disabled=(sh_pg <= 1), key="sh_prev"):
            st.session_state.sh_page = max(1, sh_pg - 1)
            st.rerun()
        pp2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {sh_pg} of {sh_total_pages}</div>", unsafe_allow_html=True)
        if pp3.button("Next ▶", disabled=(sh_pg >= sh_total_pages), key="sh_next"):
            st.session_state.sh_page = min(sh_total_pages, sh_pg + 1)
            st.rerun()


# ─────────────────────────────────────────────
#  PAGE: PRODUCT MANAGEMENT
# ─────────────────────────────────────────────

