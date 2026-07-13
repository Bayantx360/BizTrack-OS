"""
pages/inventory.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Inventory Management App
══════════════════════════════════════════════════════════════════════

Pages contained in this module:
  • Products        — catalogue, search, edit, delete with pagination
  • Add Product     — new product form with live margin preview
  • Restock         — add units to existing product + audit log
  • Restock History — searchable restock log table
  • Suppliers       — supplier directory: add, edit, delete, restock activity

Cross-app links:
  • Stockout projections pull live sales velocity via shared.db.compute_insights
  • Low-stock summary banner links back to Sales dashboard
"""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from shared.db import (
    get_products_df, get_products_df_live, get_sales_df, get_expenses_df,
    search_products, get_products_by_ids,
    compute_insights, get_insights_cached,
    db_fetch, db_insert, db_update, db_delete, clear_table_cache,
    get_restock_df, get_suppliers_df,
    TBL_PRODUCTS, TBL_RESTOCK, TBL_SUPPLIERS,
    gen_id, fmt_naira, safe_float, safe_int, fmt_qty,
)
from shared.theme import (
    apply_suite_css, kpi_card, section_header, page_header, stock_pill,
)


def page_products():
    """Products catalogue — view, edit, delete, restock, history."""
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📦 Inventory Management", "Add, edit and manage your products")

    # ── Persistent status message (survives rerun) ──
    if "inv_msg" in st.session_state:
        _msg = st.session_state.pop("inv_msg")
        (st.success if _msg.startswith(("✅", "↩️")) else st.error)(_msg)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📋 All Products", "➕ Add Product", "🔄 Restock", "📜 Restock History", "🏭 Suppliers"]
    )

    # ══════════════════════════════════════
    # Tab 1 — All Products
    # ══════════════════════════════════════
    with tab1:
        products_df = get_products_df_live(business_id)  # always live in inventory
        if products_df.empty:
            st.info("No products yet. Add your first product in the 'Add Product' tab.")
        else:
            # Summary KPIs
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                kpi_card("Total Products", str(len(products_df)), "In your catalog", icon="📦")
            with c2:
                total_sell_val = (products_df["stock_quantity"] * products_df["selling_price"]).sum()
                kpi_card("Inventory Value", fmt_naira(total_sell_val), "At selling price", icon="🏷️")
            with c3:
                total_cost_val = (products_df["stock_quantity"] * products_df["cost_price"]).sum()
                kpi_card("Inventory Cost", fmt_naira(total_cost_val), "At cost price", icon="🏦")
            with c4:
                low_count = len(products_df[products_df["stock_quantity"] <= products_df["reorder_level"]])
                kpi_card("Low Stock", str(low_count), "Need restocking",
                         positive=(low_count == 0), icon="⚠️" if low_count > 0 else "✅")

            st.markdown("---")

            # Search + category filter
            search_q     = st.text_input("🔍 Search products", key="prod_search",
                                         placeholder="Type product name…")
            cats         = ["All"] + sorted(products_df["category"].dropna().unique().tolist())
            selected_cat = st.selectbox("Filter by category", cats)

            disp = products_df if selected_cat == "All" else products_df[products_df["category"] == selected_cat]
            if search_q:
                disp = disp[disp["product_name"].str.contains(search_q, case=False, na=False)]

            # Pagination
            PAGE_SIZE   = 15
            total_pages = max(1, -(-len(disp) // PAGE_SIZE))
            if "prod_page" not in st.session_state:
                st.session_state.prod_page = 1
            if (st.session_state.get("_last_prod_search") != search_q or
                    st.session_state.get("_last_prod_cat") != selected_cat):
                st.session_state.prod_page = 1
            st.session_state["_last_prod_search"] = search_q
            st.session_state["_last_prod_cat"]    = selected_cat

            pg       = st.session_state.prod_page
            disp_page = disp.iloc[(pg-1)*PAGE_SIZE: pg*PAGE_SIZE]
            st.caption(f"Showing {len(disp_page)} of {len(disp)} products  •  Page {pg} of {total_pages}")

            for _, row in disp_page.iterrows():
                with st.expander(
                    f"**{row['product_name']}** | {row['category']} | "
                    f"Stock: {int(row['stock_quantity'])} | {fmt_naira(row['selling_price'])}",
                    expanded=False,
                ):
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        st.markdown(f"**Cost Price:** {fmt_naira(row['cost_price'])}")
                        st.markdown(f"**Selling Price (per {row.get('base_unit','unit')}):** {fmt_naira(row['selling_price'])}")
                        upp = safe_int(row.get('units_per_pack', 1))
                        if upp > 1:
                            sub_price = safe_float(row.get('selling_price_sub', 0))
                            st.markdown(f"**Selling Price (per {row.get('sub_unit','unit')}):** {fmt_naira(sub_price)}")
                        margin = safe_float(row["selling_price"]) - safe_float(row["cost_price"])
                        st.markdown(f"**Margin/unit:** {fmt_naira(margin)}")
                    with ec2:
                        upp = safe_int(row.get('units_per_pack', 1))
                        base = row.get('base_unit','unit')
                        sub  = row.get('sub_unit','unit')
                        stock_display = (
                            f"{int(row['stock_quantity'])} {base}s"
                            if upp <= 1 else
                            f"{int(row['stock_quantity'])} {base}s ({int(row['stock_quantity']) * upp} {sub}s)"
                        )
                        st.markdown(f"**Stock:** {stock_display}")
                        st.markdown(f"**Pack size:** {upp} {sub}s per {base}" if upp > 1 else f"**Unit:** {base}")
                        st.markdown(f"**Reorder Level:** {int(row['reorder_level'])} {base}s")
                        st.markdown(f"**Category:** {row['category']}")
                    with ec3:
                        st.markdown(stock_pill(row["stock_quantity"], row["reorder_level"]),
                                    unsafe_allow_html=True)

                    with st.form(f"edit_{row['product_id']}"):
                        # ── Basic Info ──
                        st.markdown("**🏷️ Basic Information**")
                        ef1, ef2    = st.columns(2)
                        new_name    = ef1.text_input("Product Name", value=row["product_name"])
                        new_cat     = ef2.text_input("Category",     value=row["category"])
                        ef3, ef4    = st.columns(2)
                        new_cost    = ef3.number_input("Cost Price (" + st.session_state.get("currency_symbol","₦") + ")", value=safe_float(row["cost_price"]),
                                                       min_value=0.0, step=50.0)
                        new_reorder = ef4.number_input("Reorder Level",  value=safe_int(row["reorder_level"]),
                                                       min_value=0, step=1)

                        st.markdown("---")

                        # ── Pack Section ──
                        st.markdown("**📦 Pack Details**")
                        pp1, pp2, pp3 = st.columns(3)
                        new_base    = pp1.text_input("Pack Unit",
                                                     value=row.get("base_unit","unit") or "unit",
                                                     help="e.g. carton, bag, crate")
                        new_upp     = pp2.number_input("Units per Pack",
                                                       value=safe_int(row.get("units_per_pack",1)) or 1,
                                                       min_value=1, step=1)
                        new_sell    = st.number_input(
                            f"Selling Price per Pack — {row.get('base_unit','unit')} ({st.session_state.get('currency_symbol','₦')})",
                            value=safe_float(row["selling_price"]), min_value=0.0, step=50.0,
                        )
                        if new_cost > 0 and new_sell > 0:
                            pm = new_sell - new_cost
                            st.caption(f"Pack margin: {fmt_naira(pm)} ({pm/new_sell*100:.1f}%)")

                        st.markdown("---")

                        # ── Unit Section ──
                        st.markdown("**🔢 Unit Details**")
                        new_sub     = st.text_input("Unit Name",
                                                    value=row.get("sub_unit","unit") or "unit",
                                                    help="e.g. piece, bottle, kg, sachet")
                        suggested   = round(new_sell / new_upp, 2) if new_upp > 1 and new_sell > 0 else new_sell
                        new_sub_price = st.number_input(
                            f"Selling Price per Unit — {row.get('sub_unit','unit')} ({st.session_state.get('currency_symbol','₦')})",
                            value=safe_float(row.get("selling_price_sub", suggested)),
                            min_value=0.0, step=50.0,
                            help=f"Suggested: {fmt_naira(suggested)} (pack ÷ {new_upp})" if new_upp > 1 else "",
                        )
                        if new_upp > 1 and new_sub_price > 0 and new_cost > 0:
                            um = new_sub_price - (new_cost / new_upp)
                            st.caption(
                                f"Unit margin: {fmt_naira(um)} | "
                                f"Selling all {new_upp} units = {fmt_naira(new_sub_price * new_upp)} "
                                f"vs pack {fmt_naira(new_sell)}"
                            )

                        st.markdown("---")

                        # ── Dates (optional) ──
                        st.markdown("**📅 Product Dates** *(optional — perishable goods only)*")
                        ed1, ed2 = st.columns(2)
                        # Safely parse existing dates; fall back to None if not set
                        _cur_mfg    = row.get("mfg_date")
                        _cur_expiry = row.get("expiry_date")
                        try:
                            _cur_mfg    = pd.to_datetime(_cur_mfg).date()    if pd.notna(_cur_mfg)    else None
                        except Exception:
                            _cur_mfg    = None
                        try:
                            _cur_expiry = pd.to_datetime(_cur_expiry).date() if pd.notna(_cur_expiry) else None
                        except Exception:
                            _cur_expiry = None
                        new_mfg_date    = ed1.date_input("Manufacturing Date",        value=_cur_mfg,    key=f"edit_mfg_{row['product_id']}")
                        new_expiry_date = ed2.date_input("Expiry / Best-Before Date", value=_cur_expiry, key=f"edit_expiry_{row['product_id']}")

                        save = st.form_submit_button("💾 Save Changes", type="primary",
                                                     width='stretch')

                    if save:
                        ok = db_update(TBL_PRODUCTS, "product_id", row["product_id"], {
                            "product_name":      new_name.strip(),
                            "category":          new_cat.strip(),
                            "cost_price":        new_cost,
                            "selling_price":     new_sell,
                            "reorder_level":     new_reorder,
                            "units_per_pack":    int(new_upp),
                            "base_unit":         new_base.strip() or "unit",
                            "sub_unit":          new_sub.strip()  or "unit",
                            "selling_price_sub": new_sub_price,
                            "mfg_date":          new_mfg_date.isoformat()    if new_mfg_date    else None,
                            "expiry_date":       new_expiry_date.isoformat()  if new_expiry_date else None,
                        })
                        if ok:
                            st.session_state["inv_msg"] = "✅ Product updated!"
                        else:
                            st.session_state["inv_msg"] = "❌ Update failed."
                        st.rerun()

                    confirm_key = f"confirm_del_{row['product_id']}"
                    if not st.session_state.get(confirm_key, False):
                        if st.button(f"🗑️ Delete {row['product_name']}", key=f"del_{row['product_id']}", type="secondary"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Delete **{row['product_name']}**? This cannot be undone.")
                        cy, cn = st.columns(2)
                        if cy.button("✅ Yes, delete", key=f"yes_del_{row['product_id']}", type="primary"):
                            ok = db_delete(TBL_PRODUCTS, "product_id", row["product_id"])
                            st.session_state.pop(confirm_key, None)
                            st.session_state["prod_del_msg"] = (
                                f"✅ {row['product_name']} deleted." if ok
                                else "❌ Failed to delete product."
                            )
                            st.rerun()
                        if cn.button("❌ Cancel", key=f"no_del_{row['product_id']}"):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()

            if "prod_del_msg" in st.session_state:
                msg = st.session_state.pop("prod_del_msg")
                (st.success if msg.startswith("✅") else st.error)(msg)

            if total_pages > 1:
                st.markdown("---")
                pc1, pc2, pc3 = st.columns([1, 3, 1])
                if pc1.button("◀ Prev", disabled=(pg <= 1), key="prod_prev"):
                    st.session_state.prod_page = max(1, pg-1); st.rerun()
                pc2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {pg} of {total_pages}</div>",
                             unsafe_allow_html=True)
                if pc3.button("Next ▶", disabled=(pg >= total_pages), key="prod_next"):
                    st.session_state.prod_page = min(total_pages, pg+1); st.rerun()

        # ── Stockout Projection (bottom of tab 1) ──
        # Uses the cached insights wrapper (60s TTL, keyed by business_id) so
        # this heavy computation runs at most once a minute — not on every
        # rerun of this tab, which previously included every keystroke typed
        # into the product search box above.
        st.markdown("---")
        section_header("📅 Stockout Projections")
        insights = get_insights_cached(business_id)

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

    # ══════════════════════════════════════
    # Tab 2 — Add Product
    # ══════════════════════════════════════
    with tab2:
        with st.form("add_product_form", clear_on_submit=True):

            # ── Basic Info ───────────────────────────────────────
            st.markdown("#### 🏷️ Basic Information")
            f1, f2      = st.columns(2)
            prod_name   = f1.text_input("Product Name *", placeholder="e.g. Coca-Cola")
            category    = f2.text_input("Category *",     placeholder="e.g. Beverages")
            f3, f4      = st.columns(2)
            cost_price  = f3.number_input("Cost Price (" + st.session_state.get("currency_symbol","₦") + ") *", min_value=0.0, step=50.0,
                                          help="What you paid per pack/unit when buying")
            reorder_lvl = f4.number_input("Reorder Level *",  min_value=0, step=1,
                                          help="Alert me when stock falls to this level")

            st.markdown("---")

            # ── Pack Section ─────────────────────────────────────
            st.markdown("#### 📦 Pack (Bulk) Details")
            st.caption("This is how you BUY the product — e.g. by carton, bag, crate.")
            p1, p2, p3  = st.columns(3)
            base_unit      = p1.text_input("Pack Unit *", value="unit",
                                           help="e.g. carton, bag, crate, dozen")
            units_per_pack = p2.number_input("Units per Pack *", min_value=1, step=1, value=1,
                                             help="How many pieces/bottles/kg in one pack")
            stock_qty      = p3.number_input("Opening Stock *", min_value=0, step=1,
                                             help="How many packs you currently have")
            sell_price     = st.number_input(
                "Selling Price per Pack (" + st.session_state.get("currency_symbol","₦") + ") *",
                min_value=0.0, step=50.0,
                help="Price charged when selling a full pack/carton/bag",
            )
            if cost_price > 0 and sell_price > 0:
                pack_margin     = sell_price - cost_price
                pack_margin_pct = (pack_margin / sell_price) * 100
                color = "green" if pack_margin >= 0 else "red"
                st.markdown(
                    f"💡 Pack margin: **{fmt_naira(pack_margin)}** ({pack_margin_pct:.1f}%)",
                )

            st.markdown("---")

            # ── Unit Section ─────────────────────────────────────
            st.markdown("#### 🔢 Unit (Individual) Details")
            st.caption(
                "This is how you SELL individually — e.g. per piece, bottle, kg. "
                "If you only sell in packs, leave Units per Pack as 1 above and set "
                "selling price per unit same as pack price."
            )
            sub_unit       = st.text_input("Unit Name *", value="unit",
                                           help="e.g. piece, bottle, sachet, kg")

            # Suggest unit price based on pack price ÷ units_per_pack
            suggested_unit_price = round(sell_price / units_per_pack, 2) if (
                units_per_pack > 1 and sell_price > 0
            ) else sell_price
            sell_price_sub = st.number_input(
                "Selling Price per Unit (" + st.session_state.get("currency_symbol","₦") + ") *",
                min_value=0.0, step=50.0,
                value=float(suggested_unit_price),
                help=(
                    f"Suggested: {fmt_naira(suggested_unit_price)} (pack price ÷ {units_per_pack}). "
                    f"You can set higher for unit-sale profit."
                ) if units_per_pack > 1 else "Price per individual item",
            )
            if units_per_pack > 1 and sell_price_sub > 0 and cost_price > 0:
                unit_cost   = cost_price / units_per_pack
                unit_margin = sell_price_sub - unit_cost
                unit_margin_pct = (unit_margin / sell_price_sub * 100) if sell_price_sub else 0
                st.markdown(
                    f"💡 Unit margin: **{fmt_naira(unit_margin)}** ({unit_margin_pct:.1f}%) "
                    f"| Selling {units_per_pack} units = **{fmt_naira(sell_price_sub * units_per_pack)}** "
                    f"vs pack price **{fmt_naira(sell_price)}**"
                )

            st.markdown("---")

            # ── Dates (optional — for perishable goods only) ──────────────────
            st.markdown("#### 📅 Product Dates *(optional)*")
            st.caption("Only for perishable goods — food, drugs, cosmetics. Leave blank if not applicable.")
            pd1, pd2 = st.columns(2)
            mfg_date_input    = pd1.date_input("Manufacturing Date",    value=None, key="add_mfg_date")
            expiry_date_input = pd2.date_input("Expiry / Best-Before Date", value=None, key="add_expiry_date")

            submitted = st.form_submit_button("➕ Add Product", width='stretch', type="primary")

        if submitted:
            if not all([prod_name.strip(), category.strip()]) or sell_price <= 0:
                st.error("Please fill all required fields and ensure selling price > 0.")
            else:
                ok = db_insert(TBL_PRODUCTS, {
                    "product_id":        gen_id("PRD"),
                    "business_id":       business_id,
                    "product_name":      prod_name.strip(),
                    "category":          category.strip(),
                    "cost_price":        cost_price,
                    "selling_price":     sell_price,
                    "selling_price_sub": sell_price_sub,
                    "stock_quantity":    stock_qty,
                    "reorder_level":     reorder_lvl,
                    "base_unit":         base_unit.strip() or "unit",
                    "sub_unit":          sub_unit.strip()  or "unit",
                    "units_per_pack":    int(units_per_pack),
                    "mfg_date":          mfg_date_input.isoformat()    if mfg_date_input    else None,
                    "expiry_date":       expiry_date_input.isoformat()  if expiry_date_input else None,
                    "created_at":        datetime.now().isoformat(),
                })
                if ok:
                    st.session_state["inv_msg"] = (
                        f"✅ '{prod_name}' added! "
                        f"Pack: {fmt_naira(sell_price)} per {base_unit} | "
                        f"Unit: {fmt_naira(sell_price_sub)} per {sub_unit}"
                    )
                    st.rerun()
                else:
                    st.error("Failed to add product. Please try again.")

    # ══════════════════════════════════════
    # Tab 3 — Restock
    # ══════════════════════════════════════
    with tab3:
        st.markdown("#### 🔄 Restock a Product")

        # ── Product search + selector (outside form for reactivity) ──
        restock_search = st.text_input(
            "🔍 Search product to restock",
            placeholder="Type product name…",
            key="restock_search_query",
        )

        search_term = restock_search.strip()
        # Indexed, bounded search — cost stays flat whether the catalogue
        # has 50 SKUs or 5,000. in_stock_only=False since restocking is
        # exactly when a product IS low/out of stock. Empty query shows a
        # small default page instead of the whole catalogue, so the
        # selectbox never has to render thousands of options. This single
        # call also tells us whether the business has any products at all —
        # no separate existence-check round-trip needed.
        filtered_df = search_products(business_id, search_term, limit=30)

        if filtered_df.empty:
            if search_term:
                st.warning("⚠️ No products match your search. Try a different name.")
            else:
                st.info("No products found. Add products first.")
            st.stop()

        product_options = {
            f"{r['product_name']} ({r.get('base_unit','unit')}s)": r
            for _, r in filtered_df.iterrows()
        }

        # Auto-select when search narrows to exactly one match
        if len(product_options) == 1:
            selected_label   = list(product_options.keys())[0]
            selected_product = product_options[selected_label]
            st.info(f"✅ Matched: **{selected_label}**")
        else:
            selected_label   = st.selectbox(
                "Select product to restock",
                list(product_options.keys()),
                key="restock_product_select",
            )
            selected_product = product_options[selected_label]

        cur_cost      = safe_float(selected_product["cost_price"])
        cur_sell_pack = safe_float(selected_product["selling_price"])
        cur_sell_unit = safe_float(selected_product.get("selling_price_sub", 0))
        cur_stock     = safe_float(selected_product["stock_quantity"])
        base_unit     = selected_product.get("base_unit", "unit") or "unit"
        sub_unit      = selected_product.get("sub_unit",  "unit") or "unit"
        upp           = safe_int(selected_product.get("units_per_pack", 1)) or 1

        # Current stock — compact single line, no truncation
        if upp > 1:
            stock_str = (
                f"{fmt_qty(cur_stock)} {base_unit}s "
                f"({int(round(cur_stock * upp))} {sub_unit}s)"
            )
        else:
            stock_str = f"{fmt_qty(cur_stock)} {base_unit}s"
        st.caption(f"📦 Current stock: **{stock_str}**")

        # ── Recent deliveries panel (reactive to product selection) ──
        hist_df = get_restock_df(business_id)
        if not hist_df.empty:
            pid          = selected_product["product_id"]
            product_hist = hist_df[hist_df["product_id"] == pid].copy()
            product_hist = product_hist.sort_values("restock_date", ascending=False).head(5)

            if not product_hist.empty:
                with st.expander(
                    f"📋 Last {len(product_hist)} deliver{'y' if len(product_hist) == 1 else 'ies'} "
                    f"for **{selected_product['product_name']}**",
                    expanded=True,
                ):
                    for _, h in product_hist.iterrows():
                        date_str     = str(h.get("restock_date", ""))[:10] or "—"
                        qty          = int(h.get("qty_added", 0))
                        sup          = h.get("supplier_name", "") or "No supplier recorded"
                        note         = h.get("note", "") or ""
                        note_snippet = f" · _{note}_" if note else ""
                        st.markdown(
                            f"**{date_str}** &nbsp;·&nbsp; "
                            f"+{qty} {base_unit}s &nbsp;·&nbsp; "
                            f"🏭 {sup}{note_snippet}"
                        )

        st.markdown("---")

        # ── Supplier selector (outside form for reactivity) ──
        st.markdown("**🏭 Supplier**")
        suppliers_df = get_suppliers_df(business_id)

        add_new_supplier = st.checkbox(
            "➕ New supplier — add to directory",
            value=False,
            key="restock_new_supplier_toggle",
        )

        if add_new_supplier:
            ns1, ns2 = st.columns(2)
            new_sup_name  = ns1.text_input(
                "Supplier Name *",
                placeholder="e.g. Alhaji Musa Traders",
                key="new_sup_name",
            )
            new_sup_phone = ns2.text_input(
                "Phone *",
                placeholder="e.g. 0801 234 5678",
                key="new_sup_phone",
            )
            new_sup_notes = st.text_input(
                "Notes (optional)",
                placeholder="e.g. Cash on delivery only",
                key="new_sup_notes",
            )
            selected_supplier_id   = None
            selected_supplier_name = new_sup_name.strip() or "—"
        else:
            if suppliers_df.empty:
                st.info("No suppliers saved yet. Tick the box above to add your first one.")
                selected_supplier_id   = None
                selected_supplier_name = ""
            else:
                sup_options = {
                    f"{r['name']}  •  {r.get('phone', '')}": r
                    for _, r in suppliers_df.iterrows()
                }
                sup_label            = st.selectbox(
                    "Select supplier",
                    list(sup_options.keys()),
                    key="restock_supplier_select",
                )
                selected_supplier_id   = sup_options[sup_label]["supplier_id"]
                selected_supplier_name = sup_options[sup_label]["name"]

        st.markdown("---")

        # ── Delivery fields (outside form for reactivity) ──
        st.markdown("**📥 New Delivery**")

        if upp > 1:
            restock_mode = st.radio(
                "Received as",
                options=["base", "sub"],
                format_func=lambda x: (
                    f"Full {base_unit}s" if x == "base"
                    else f"Individual {sub_unit}s"
                ),
                horizontal=True,
                key="restock_mode",
                help=f"Use '{sub_unit}s' if you received a partial "
                     f"{base_unit} (e.g. only 3 out of {upp}).",
            )
        else:
            restock_mode = "base"

        rd1, rd2 = st.columns(2)

        if restock_mode == "sub":
            add_qty_raw = rd1.number_input(
                f"{sub_unit.capitalize()}s Received *",
                min_value=1, step=1, value=upp,
                key="restock_add_qty_sub",
                help=f"Number of individual {sub_unit}s received "
                     f"({upp} {sub_unit}s = 1 {base_unit})",
            )
            add_qty = add_qty_raw / upp  # fractional base units
            rd1.caption(f"= **{fmt_qty(add_qty)} {base_unit}s**")
        else:
            add_qty = rd1.number_input(
                f"Packs Received ({base_unit}s) *",
                min_value=1, step=1, value=10,
                key="restock_add_qty",
                help=f"Number of {base_unit}s received from supplier",
            )

        restock_note = rd2.text_input(
            "Batch Note (optional)",
            placeholder="e.g. 3 cartons were dented",
            key="restock_note",
        )

        st.markdown("---")

        # ── Price update (outside form so checkbox reacts immediately) ──
        st.markdown("**💰 Update Prices**")
        update_prices = st.checkbox(
            "Supplier prices have changed — update now",
            value=False,
            key="restock_update_prices",
            help="Tick this if cost or selling prices changed with this delivery",
        )

        if update_prices:
            # Current prices reference — visible only when user is editing prices
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("Current Cost",      fmt_naira(cur_cost),      help=f"Per {base_unit}")
            pc2.metric("Current Sell/Pack",  fmt_naira(cur_sell_pack), help=f"Per {base_unit}")
            pc3.metric("Current Sell/Unit",  fmt_naira(cur_sell_unit), help=f"Per {sub_unit}")
            st.caption("Pre-filled with current prices. Edit only what changed.")

            new_cost = st.number_input(
                f"New Cost Price per {base_unit} ({st.session_state.get('currency_symbol','₦')})",
                min_value=0.0, step=50.0, value=float(cur_cost),
                key="restock_new_cost",
            )
            if new_cost != cur_cost and cur_cost > 0:
                diff = new_cost - cur_cost
                pct  = diff / cur_cost * 100
                icon = "📈 Cost UP" if diff > 0 else "📉 Cost DOWN"
                st.caption(f"{icon} by {fmt_naira(abs(diff))} ({abs(pct):.1f}%)")

            st.markdown("**Pack Selling Price**")
            new_sell_pack = st.number_input(
                f"New Selling Price per {base_unit} ({st.session_state.get('currency_symbol','₦')})",
                min_value=0.0, step=50.0, value=float(cur_sell_pack),
                key="restock_new_sell_pack",
            )
            if new_cost > 0 and new_sell_pack > 0:
                pm = new_sell_pack - new_cost
                st.caption(
                    f"New pack margin: {fmt_naira(pm)} ({pm/new_sell_pack*100:.1f}%)"
                )

            st.markdown("**Unit Selling Price**")
            suggested_unit = round(new_sell_pack / upp, 2) if upp > 1 else new_sell_pack
            new_sell_unit  = st.number_input(
                f"New Selling Price per {sub_unit} ({st.session_state.get('currency_symbol','₦')})",
                min_value=0.0, step=50.0,
                value=float(cur_sell_unit) if cur_sell_unit > 0 else float(suggested_unit),
                key="restock_new_sell_unit",
                help=f"Suggested: {fmt_naira(suggested_unit)}" if upp > 1 else "",
            )
            if upp > 1 and new_sell_unit > 0 and new_cost > 0:
                um = new_sell_unit - (new_cost / upp)
                st.caption(
                    f"New unit margin: {fmt_naira(um)} | "
                    f"All {upp} units = {fmt_naira(new_sell_unit * upp)} "
                    f"vs pack {fmt_naira(new_sell_pack)}"
                )
        else:
            new_cost      = cur_cost
            new_sell_pack = cur_sell_pack
            new_sell_unit = cur_sell_unit

        st.markdown("---")

        # ── Expiry date update (optional — for perishable goods) ──────────
        st.markdown("**📅 New Batch Dates** *(optional)*")
        st.caption("New delivery? Update expiry if this batch has a different date. Leave blank to keep current.")
        _existing_expiry = selected_product.get("expiry_date")
        _existing_mfg    = selected_product.get("mfg_date")
        try:
            _existing_expiry = pd.to_datetime(_existing_expiry).date() if pd.notna(_existing_expiry) else None
        except Exception:
            _existing_expiry = None
        try:
            _existing_mfg = pd.to_datetime(_existing_mfg).date() if pd.notna(_existing_mfg) else None
        except Exception:
            _existing_mfg = None
        rb1, rb2 = st.columns(2)
        restock_mfg_date    = rb1.date_input("Manufacturing Date",        value=_existing_mfg,    key="restock_mfg_date")
        restock_expiry_date = rb2.date_input("Expiry / Best-Before Date", value=_existing_expiry, key="restock_expiry_date")

        st.markdown("---")

        # ── Submit button inside the form ──
        with st.form("restock_form", clear_on_submit=True):
            submitted = st.form_submit_button(
                "🔄 Confirm Restock", width='stretch', type="primary"
            )

            if submitted:
                # Validate supplier fields if adding new
                if add_new_supplier:
                    if not new_sup_name.strip() or not new_sup_phone.strip():
                        st.error("Please enter the new supplier's name and phone number.")
                        st.stop()
                    # Save new supplier to directory
                    new_sup_id = gen_id("SUP")
                    sup_saved  = db_insert(TBL_SUPPLIERS, {
                        "supplier_id": new_sup_id,
                        "business_id": business_id,
                        "name":        new_sup_name.strip(),
                        "phone":       new_sup_phone.strip(),
                        "notes":       new_sup_notes.strip() if new_sup_notes else "",
                        "created_at":  datetime.now().isoformat(),
                    })
                    if not sup_saved:
                        st.error("Failed to save new supplier. Please try again.")
                        st.stop()
                    resolved_supplier_id   = new_sup_id
                    resolved_supplier_name = new_sup_name.strip()
                else:
                    resolved_supplier_id   = selected_supplier_id   or ""
                    resolved_supplier_name = selected_supplier_name or ""

                if upp > 1:
                    new_qty = round(cur_stock + add_qty, 4)
                else:
                    new_qty = int(round(cur_stock + add_qty))
                updates = {"stock_quantity": new_qty}
                if update_prices:
                    updates["cost_price"]        = new_cost
                    updates["selling_price"]     = new_sell_pack
                    updates["selling_price_sub"] = new_sell_unit
                # Always write dates (None clears them, a value updates them)
                updates["mfg_date"]    = restock_mfg_date.isoformat()    if restock_mfg_date    else None
                updates["expiry_date"] = restock_expiry_date.isoformat()  if restock_expiry_date else None

                _auto_note = (
                    f"Received {add_qty_raw} {sub_unit}(s) "
                    f"(= {fmt_qty(add_qty)} {base_unit}s)"
                    if restock_mode == "sub" else ""
                )
                _final_note = " | ".join(
                    n for n in [restock_note.strip() if restock_note else "", _auto_note] if n
                )

                ok = db_update(TBL_PRODUCTS, "product_id",
                               selected_product["product_id"], updates)
                if ok:
                    db_insert(TBL_RESTOCK, {
                        "restock_id":    gen_id("RST"),
                        "business_id":   business_id,
                        "product_id":    selected_product["product_id"],
                        "product_name":  selected_product["product_name"],
                        "qty_added":     add_qty if upp > 1 else int(add_qty),
                        "qty_before":    cur_stock if upp > 1 else int(cur_stock),
                        "qty_after":     new_qty if upp > 1 else int(new_qty),
                        "supplier_id":   resolved_supplier_id,
                        "supplier_name": resolved_supplier_name,
                        "note":          _final_note,
                        "recorded_by":   user.get("full_name", user.get("email", "")),
                        "restock_date":  datetime.now().isoformat(),
                    })
                    msg = (
                        f"✅ Restocked! {selected_product['product_name']}: "
                        f"{fmt_qty(cur_stock)} → {fmt_qty(new_qty)} {base_unit}s"
                    )
                    if resolved_supplier_name:
                        msg += f" | Supplier: {resolved_supplier_name}"
                    if update_prices:
                        msg += (
                            f" | Prices updated — Cost: {fmt_naira(new_cost)}, "
                            f"Pack: {fmt_naira(new_sell_pack)}, "
                            f"Unit: {fmt_naira(new_sell_unit)}"
                        )
                    st.success(msg)
                else:
                    st.error("Failed to update stock.")

    # ══════════════════════════════════════
    # Tab 4 — Restock History
    # ══════════════════════════════════════
    with tab4:
        section_header("📜 Restock History")
        restock_df = get_restock_df(business_id)
        if restock_df.empty:
            st.info("No restock history yet. Every restock will be logged here automatically.")
        else:
            restock_df = restock_df.sort_values("restock_date", ascending=False)

            # ── Filters ──
            f1, f2 = st.columns(2)
            search_rst = f1.text_input("🔍 Search by product name", key="restock_search",
                                       placeholder="Type to filter…")
            # Supplier filter — only shown when supplier_name column exists and has data
            sup_filter = ""
            if "supplier_name" in restock_df.columns:
                sup_names   = sorted(restock_df["supplier_name"].dropna().unique().tolist())
                sup_names   = [s for s in sup_names if s.strip()]
                if sup_names:
                    sup_options = ["All suppliers"] + sup_names
                    sup_filter  = f2.selectbox("🏭 Filter by supplier", sup_options,
                                               key="restock_sup_filter")

            if search_rst:
                restock_df = restock_df[
                    restock_df["product_name"].str.contains(search_rst, case=False, na=False)
                ]
            if sup_filter and sup_filter != "All suppliers":
                restock_df = restock_df[restock_df["supplier_name"] == sup_filter]

            # ── Per-row display with Reverse button ──
            for _, row in restock_df.iterrows():
                restock_id     = row.get("restock_id", "")
                product_id     = row.get("product_id", "")
                product_name   = row.get("product_name", "")
                qty_added      = int(row.get("qty_added", 0))
                qty_before     = int(row.get("qty_before", 0))
                qty_after      = int(row.get("qty_after",  0))
                note           = row.get("note", "") or ""
                recorded_by    = row.get("recorded_by", "") or ""
                supplier_name  = row.get("supplier_name", "") or ""
                r_date         = row.get("restock_date", "")
                date_str       = str(r_date)[:16] if r_date else "—"

                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(
                            f"**{product_name}** &nbsp;|&nbsp; "
                            f"📅 {date_str} &nbsp;|&nbsp; "
                            f"➕ {qty_added} units &nbsp;|&nbsp; "
                            f"{qty_before} → {qty_after}"
                        )
                        meta_parts = []
                        if supplier_name:
                            meta_parts.append(f"🏭 {supplier_name}")
                        if note:
                            meta_parts.append(f"📝 {note}")
                        meta_parts.append(f"👤 {recorded_by}")
                        st.caption("  •  ".join(meta_parts))
                    with c2:
                        if st.button("↩️ Reverse", key=f"rev_{restock_id}", type="secondary"):
                            current_df  = get_products_by_ids(business_id, [product_id])
                            product_row = current_df[current_df["product_id"] == product_id]
                            if product_row.empty:
                                st.error("Product not found.")
                            else:
                                current_stock = safe_float(product_row.iloc[0]["stock_quantity"])
                                restored_qty  = max(0, int(current_stock) - qty_added)
                                ok = db_update(
                                    TBL_PRODUCTS, "product_id", product_id,
                                    {"stock_quantity": restored_qty}
                                )
                                if ok:
                                    db_delete(TBL_RESTOCK, "restock_id", restock_id)
                                    st.session_state["inv_msg"] = (
                                        f"↩️ Reversed! {product_name} stock: "
                                        f"{int(current_stock)} → {restored_qty}"
                                    )
                                    st.rerun()

    # ══════════════════════════════════════
    # Tab 5 — Suppliers
    # ══════════════════════════════════════
    with tab5:
        page_header("🏭 Suppliers", "Your supplier directory")

        suppliers_df = get_suppliers_df(business_id)
        restock_df   = get_restock_df(business_id)

        # ── Summary KPIs ──
        total_suppliers = len(suppliers_df) if not suppliers_df.empty else 0
        if not restock_df.empty and "supplier_name" in restock_df.columns:
            active_suppliers = restock_df["supplier_name"].dropna().nunique()
        else:
            active_suppliers = 0

        k1, k2 = st.columns(2)
        with k1:
            kpi_card("Total Suppliers", str(total_suppliers), "In your directory", icon="🏭")
        with k2:
            kpi_card("Active Suppliers", str(active_suppliers), "Have made at least one delivery", icon="📦")

        st.markdown("---")

        # ── Add New Supplier form ──
        section_header("➕ Add New Supplier")
        with st.form("add_supplier_form", clear_on_submit=True):
            af1, af2 = st.columns(2)
            sup_name  = af1.text_input("Supplier Name *", placeholder="e.g. Alhaji Musa Traders")
            sup_phone = af2.text_input("Phone *",         placeholder="e.g. 0801 234 5678")
            sup_notes = st.text_input("Notes (optional)", placeholder="e.g. Cash on delivery only, delivers Tuesdays")
            add_sup   = st.form_submit_button("➕ Add Supplier", type="primary", width="stretch")

        if add_sup:
            if not sup_name.strip() or not sup_phone.strip():
                st.error("Please enter both name and phone number.")
            else:
                # Guard against duplicates (same name + phone for this business)
                if not suppliers_df.empty:
                    dup = suppliers_df[
                        (suppliers_df["name"].str.lower()  == sup_name.strip().lower()) &
                        (suppliers_df["phone"].str.strip() == sup_phone.strip())
                    ]
                    if not dup.empty:
                        st.warning(f"⚠️ A supplier named **{sup_name.strip()}** with that phone already exists.")
                        st.stop()
                ok = db_insert(TBL_SUPPLIERS, {
                    "supplier_id": gen_id("SUP"),
                    "business_id": business_id,
                    "name":        sup_name.strip(),
                    "phone":       sup_phone.strip(),
                    "notes":       sup_notes.strip() if sup_notes else "",
                    "created_at":  datetime.now().isoformat(),
                })
                if ok:
                    st.success(f"✅ {sup_name.strip()} added to your supplier directory.")
                    st.rerun()
                else:
                    st.error("Failed to add supplier. Please try again.")

        st.markdown("---")

        # ── Supplier directory list ──
        section_header("📋 Your Suppliers")

        if suppliers_df.empty:
            st.info("No suppliers yet. Add your first supplier above.")
        else:
            # Build restock activity summary per supplier for inline display
            activity = {}
            if not restock_df.empty and "supplier_name" in restock_df.columns:
                for sup_name_key, grp in restock_df.groupby("supplier_name"):
                    activity[sup_name_key] = {
                        "count":    len(grp),
                        "last":     str(grp["restock_date"].max())[:10],
                    }

            search_sup = st.text_input("🔍 Search suppliers", placeholder="Type name…",
                                       key="sup_dir_search")
            disp_sup   = suppliers_df
            if search_sup.strip():
                disp_sup = suppliers_df[
                    suppliers_df["name"].str.contains(search_sup.strip(), case=False, na=False)
                ]

            if disp_sup.empty:
                st.warning("No suppliers match your search.")
            else:
                for _, row in disp_sup.iterrows():
                    sid        = row["supplier_id"]
                    sname      = row.get("name",  "")
                    sphone     = row.get("phone", "")
                    snotes     = row.get("notes", "") or ""
                    act        = activity.get(sname, {})
                    restock_ct = act.get("count", 0)
                    last_del   = act.get("last",  "No deliveries yet")

                    with st.expander(
                        f"**{sname}** &nbsp;|&nbsp; 📞 {sphone}"
                        + (f" &nbsp;|&nbsp; {restock_ct} delivery" + ("" if restock_ct == 1 else "ies") if restock_ct else ""),
                        expanded=False,
                    ):
                        ic1, ic2 = st.columns(2)
                        ic1.markdown(f"**Phone:** {sphone}")
                        ic2.markdown(f"**Last Delivery:** {last_del}")
                        if snotes:
                            st.markdown(f"**Notes:** {snotes}")
                        st.markdown(f"**Total Deliveries:** {restock_ct}")

                        # ── Edit form ──
                        with st.form(f"edit_sup_{sid}"):
                            st.markdown("**✏️ Edit Supplier**")
                            ef1, ef2  = st.columns(2)
                            new_name  = ef1.text_input("Name",  value=sname)
                            new_phone = ef2.text_input("Phone", value=sphone)
                            new_notes = st.text_input("Notes", value=snotes)
                            save_sup  = st.form_submit_button("💾 Save Changes", type="primary",
                                                              width="stretch")

                        if save_sup:
                            if not new_name.strip() or not new_phone.strip():
                                st.error("Name and phone are required.")
                            else:
                                ok = db_update(TBL_SUPPLIERS, "supplier_id", sid, {
                                    "name":  new_name.strip(),
                                    "phone": new_phone.strip(),
                                    "notes": new_notes.strip() if new_notes else "",
                                })
                                if ok:
                                    st.success("✅ Supplier updated.")
                                    st.rerun()
                                else:
                                    st.error("Failed to update supplier.")

                        # ── Delete ──
                        confirm_key = f"confirm_del_sup_{sid}"
                        if not st.session_state.get(confirm_key, False):
                            if st.button(f"🗑️ Delete {sname}", key=f"del_sup_{sid}",
                                         type="secondary"):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            st.warning(
                                f"⚠️ Delete **{sname}**? Their restock history will be kept "
                                f"but will no longer link to a directory entry."
                            )
                            cy, cn = st.columns(2)
                            if cy.button("✅ Yes, delete", key=f"yes_del_sup_{sid}",
                                         type="primary"):
                                ok = db_delete(TBL_SUPPLIERS, "supplier_id", sid)
                                st.session_state.pop(confirm_key, None)
                                if ok:
                                    st.success(f"✅ {sname} removed from directory.")
                                else:
                                    st.error("Failed to delete supplier.")
                                st.rerun()
                            if cn.button("❌ Cancel", key=f"no_del_sup_{sid}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
