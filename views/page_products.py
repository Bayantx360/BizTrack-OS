# ============================================================
#  pages/page_products.py
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


def page_products():
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📦 Product Management", "Add, edit and manage your inventory")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 All Products", "➕ Add Product", "🔄 Restock", "📜 Restock History"])

    # ── Tab 1: View All ──
    with tab1:
        products_df = get_products_df(business_id)
        if products_df.empty:
            st.info("No products yet. Add your first product in the 'Add Product' tab.")
        else:
            # Summary metrics
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                kpi_card("Total Products", str(len(products_df)), "In your catalog")
            with c2:
                total_stock_val = (products_df["stock_quantity"] * products_df["selling_price"]).sum()
                kpi_card("Inventory Value", fmt_naira(total_stock_val), "At selling price")
            with c3:
                total_cost_val = (products_df["stock_quantity"] * products_df["cost_price"]).sum()
                kpi_card("Inventory Cost", fmt_naira(total_cost_val), "At cost price")
            with c4:
                low_count = len(products_df[products_df["stock_quantity"] <= products_df["reorder_level"]])
                kpi_card("Low Stock", str(low_count), "Need restocking", positive=(low_count == 0))

            st.markdown("---")

            # Category filter + search
            search_q = st.text_input("🔍 Search products", key="prod_search", placeholder="Type product name…")
            cats = ["All"] + sorted(products_df["category"].unique().tolist())
            selected_cat = st.selectbox("Filter by category", cats)
            disp = products_df if selected_cat == "All" else products_df[products_df["category"] == selected_cat]
            if search_q:
                disp = disp[disp["product_name"].str.contains(search_q, case=False, na=False)]

            # Pagination
            PAGE_SIZE = 15
            total_pages = max(1, -(-len(disp) // PAGE_SIZE))  # ceiling division
            if "prod_page" not in st.session_state:
                st.session_state.prod_page = 1
            # Reset page if filter changes
            if st.session_state.get("_last_prod_search") != search_q or st.session_state.get("_last_prod_cat") != selected_cat:
                st.session_state.prod_page = 1
            st.session_state["_last_prod_search"] = search_q
            st.session_state["_last_prod_cat"] = selected_cat

            pg = st.session_state.prod_page
            start_idx = (pg - 1) * PAGE_SIZE
            disp_page = disp.iloc[start_idx: start_idx + PAGE_SIZE]

            st.caption(f"Showing {len(disp_page)} of {len(disp)} products  •  Page {pg} of {total_pages}")

            # Display product cards
            for _, row in disp_page.iterrows():
                with st.expander(
                    f"**{row['product_name']}** | {row['category']} | "
                    f"Stock: {int(row['stock_quantity'])} | {fmt_naira(row['selling_price'])}",
                    expanded=False
                ):
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        st.markdown(f"**Cost Price:** {fmt_naira(row['cost_price'])}")
                        st.markdown(f"**Selling Price:** {fmt_naira(row['selling_price'])}")
                        margin = safe_float(row['selling_price']) - safe_float(row['cost_price'])
                        st.markdown(f"**Margin/unit:** {fmt_naira(margin)}")
                    with ec2:
                        st.markdown(f"**Stock:** {int(row['stock_quantity'])} units")
                        st.markdown(f"**Reorder Level:** {int(row['reorder_level'])} units")
                        st.markdown(f"**Category:** {row['category']}")
                    with ec3:
                        st.markdown(
                            stock_pill(row["stock_quantity"], row["reorder_level"]),
                            unsafe_allow_html=True
                        )

                    # Edit form
                    with st.form(f"edit_{row['product_id']}"):
                        st.markdown("**Edit Product**")
                        f1, f2 = st.columns(2)
                        new_name     = f1.text_input("Product Name", value=row["product_name"])
                        new_cat      = f2.text_input("Category",     value=row["category"])
                        new_cost     = f1.number_input("Cost Price",    value=safe_float(row["cost_price"]),    min_value=0.0, step=50.0)
                        new_sell     = f2.number_input("Selling Price", value=safe_float(row["selling_price"]), min_value=0.0, step=50.0)
                        new_reorder  = f1.number_input("Reorder Level", value=safe_int(row["reorder_level"]),   min_value=0,   step=1)
                        save = st.form_submit_button("💾 Save Changes", type="primary")

                    if save:
                        ok = db_update(TBL_PRODUCTS, "product_id", row["product_id"], {
                                "product_name": new_name, "category": new_cat,
                                "cost_price": new_cost, "selling_price": new_sell,
                                "reorder_level": new_reorder,
                            })
                        st.success("Product updated!") if ok else st.error("Update failed.")
                        st.rerun()

                    confirm_key = f"confirm_del_{row['product_id']}"
                    if not st.session_state.get(confirm_key, False):
                        if st.button(f"🗑️ Delete {row['product_name']}", key=f"del_{row['product_id']}"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Are you sure you want to delete **{row['product_name']}**? This cannot be undone.")
                        c_yes, c_no = st.columns(2)
                        if c_yes.button("✅ Yes, delete", key=f"yes_del_{row['product_id']}", type="primary"):
                            ok = db_delete(TBL_PRODUCTS, "product_id", row["product_id"])
                            st.cache_data.clear()
                            st.session_state.pop(confirm_key, None)
                            st.session_state["prod_del_msg"] = (
                                f"✅ {row['product_name']} deleted successfully."
                                if ok else "❌ Failed to delete product. Please try again."
                            )
                            st.rerun()
                        if c_no.button("❌ Cancel", key=f"no_del_{row['product_id']}"):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()

            # Show product delete feedback
            if "prod_del_msg" in st.session_state:
                msg = st.session_state.pop("prod_del_msg")
                if msg.startswith("✅"):
                    st.success(msg)
                else:
                    st.error(msg)

            # Pagination controls
            if total_pages > 1:
                st.markdown("---")
                pc1, pc2, pc3 = st.columns([1, 3, 1])
                if pc1.button("◀ Prev", disabled=(pg <= 1), key="prod_prev"):
                    st.session_state.prod_page = max(1, pg - 1)
                    st.rerun()
                pc2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {pg} of {total_pages}</div>", unsafe_allow_html=True)
                if pc3.button("Next ▶", disabled=(pg >= total_pages), key="prod_next"):
                    st.session_state.prod_page = min(total_pages, pg + 1)
                    st.rerun()

    # ── Tab 2: Add Product ──
    with tab2:
        with st.form("add_product_form", clear_on_submit=True):
            st.markdown("#### New Product Details")
            f1, f2 = st.columns(2)
            prod_name   = f1.text_input("Product Name *",     placeholder="e.g. Indomie Chicken 70g")
            category    = f2.text_input("Category *",         placeholder="e.g. Noodles, Beverages")
            cost_price  = f1.number_input("Cost Price (₦) *",    min_value=0.0, step=50.0,
                                          help="What you paid per unit")
            sell_price  = f2.number_input("Selling Price (₦) *", min_value=0.0, step=50.0,
                                          help="What the customer pays")
            stock_qty   = f1.number_input("Opening Stock *",  min_value=0, step=1,
                                          help="How many units you have right now")
            reorder_lvl = f2.number_input("Reorder Level *",  min_value=0, step=1,
                                          help="Alert me when stock falls to this level")

            if cost_price > 0 and sell_price > 0:
                margin  = sell_price - cost_price
                margin_pct = (margin / sell_price) * 100
                st.info(f"💡 Profit margin: **{fmt_naira(margin)}** per unit ({margin_pct:.1f}%)")

            submitted = st.form_submit_button("➕ Add Product", use_container_width=True, type="primary")

        if submitted:
            if not all([prod_name, category]) or sell_price <= 0:
                st.error("Please fill in all required fields and ensure selling price > 0.")
            else:
                product_id = gen_id("PRD")
                ok = db_insert(TBL_PRODUCTS, {
                    "product_id":     product_id,
                    "business_id":    business_id,
                    "product_name":   prod_name.strip(),
                    "category":       category.strip(),
                    "cost_price":     cost_price,
                    "selling_price":  sell_price,
                    "stock_quantity": stock_qty,
                    "reorder_level":  reorder_lvl,
                    "created_at":     datetime.now().isoformat(),
                })
                if ok:
                    st.success(f"✅ '{prod_name}' added to your inventory!")
                    st.rerun()
                else:
                    st.error("Failed to add product. Please try again.")

    # ── Tab 3: Restock ──
    with tab3:
        products_df = get_products_df(business_id)
        if products_df.empty:
            st.info("No products found. Add products first.")
        else:
            st.markdown("#### Add Stock to Existing Product")
            with st.form("restock_form", clear_on_submit=True):
                product_options = {
                    f"{r['product_name']} (Current: {int(r['stock_quantity'])} units)": r
                    for _, r in products_df.iterrows()
                }
                selected_label   = st.selectbox("Select product", list(product_options.keys()))
                selected_product = product_options[selected_label]

                add_qty = st.number_input("Units to add", min_value=1, step=1, value=10)
                restock_note = st.text_input("Note (optional)", placeholder="e.g. Weekly supplier delivery")
                submitted = st.form_submit_button("🔄 Update Stock", use_container_width=True, type="primary")

            if submitted:
                new_qty = int(selected_product["stock_quantity"]) + add_qty
                ok = db_update(TBL_PRODUCTS, "product_id", selected_product["product_id"], {"stock_quantity": new_qty})
                if ok:
                    # Log the restock event for audit trail
                    db_insert(TBL_RESTOCK, {
                        "restock_id":   gen_id("RST"),
                        "business_id":  business_id,
                        "product_id":   selected_product["product_id"],
                        "product_name": selected_product["product_name"],
                        "qty_added":    add_qty,
                        "qty_before":   int(selected_product["stock_quantity"]),
                        "qty_after":    new_qty,
                        "note":         restock_note.strip() if restock_note else "",
                        "recorded_by":  user.get("full_name", user.get("email", "")),
                        "restock_date": datetime.now().isoformat(),
                    })
                    st.success(
                        f"✅ Stock updated! {selected_product['product_name']}: "
                        f"{int(selected_product['stock_quantity'])} → {new_qty} units"
                    )
                    st.rerun()
                else:
                    st.error("Failed to update stock.")

    # ── Tab 4: Restock History ──
    with tab4:
        section_header("📜 Restock History")
        restock_df = db_fetch(TBL_RESTOCK, {"business_id": business_id})
        if restock_df.empty:
            st.info("No restock history yet. Every restock will be logged here automatically.")
        else:
            restock_df["restock_date"] = pd.to_datetime(restock_df["restock_date"], errors="coerce", utc=True).dt.tz_localize(None)
            restock_df = restock_df.sort_values("restock_date", ascending=False)

            # Search
            search_rst = st.text_input("🔍 Search by product name", key="restock_search", placeholder="Type to filter…")
            if search_rst:
                restock_df = restock_df[restock_df["product_name"].str.contains(search_rst, case=False, na=False)]

            display_cols = [c for c in ["restock_date","product_name","qty_before","qty_added","qty_after","note","recorded_by"] if c in restock_df.columns]
            st.dataframe(
                restock_df[display_cols].rename(columns={
                    "restock_date":  "Date",
                    "product_name":  "Product",
                    "qty_before":    "Stock Before",
                    "qty_added":     "Units Added",
                    "qty_after":     "Stock After",
                    "note":          "Note",
                    "recorded_by":   "Recorded By",
                }),
                use_container_width=True,
            )


# ─────────────────────────────────────────────
#  PAGE: EXPENSES
# ─────────────────────────────────────────────

