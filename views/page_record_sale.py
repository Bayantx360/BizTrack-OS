# ============================================================
#  pages/page_record_sale.py
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


def page_record_sale():
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("🛒 Record a Sale", "Build a cart, apply discounts, print receipt")

    products_df = get_products_df(business_id)
    if products_df.empty:
        st.warning("No products found. Please add products first.")
        return

    # ── Session state cart ──
    if "cart" not in st.session_state:
        st.session_state.cart = []
    if "sale_done" not in st.session_state:
        st.session_state.sale_done = None  # holds receipt data after recording

    col1, col2 = st.columns([3, 2], gap="large")

    # ════════════════════════════════════
    #  LEFT: Product selector + cart
    # ════════════════════════════════════
    with col1:
        section_header("🛍️ Build Cart")

        # Product selector form
        in_stock = products_df[products_df["stock_quantity"] > 0]
        if in_stock.empty:
            st.warning("All products are out of stock.")
        else:
            prod_names = in_stock["product_name"].tolist()

            # ── Product selector OUTSIDE form so price updates on change ──
            sel_name = st.selectbox("Product", prod_names, key="cart_prod")
            sel_prod_row   = in_stock[in_stock["product_name"] == sel_name].iloc[0]
            original_price = safe_float(sel_prod_row["selling_price"])
            avail_qty      = int(sel_prod_row["stock_quantity"])

            # Already-in-cart qty for this product
            already_in_cart = sum(
                i["quantity"] for i in st.session_state.cart
                if i["product_id"] == sel_prod_row["product_id"]
            )
            remaining = avail_qty - already_in_cart
            st.caption(
                f"📦 Listed price: **{fmt_naira(original_price)}** "
                f"&nbsp;|&nbsp; 🏷️ Stock available: **{remaining} units**"
            )

            # ── Qty + price inside form ──
            with st.form("add_to_cart", clear_on_submit=True):
                ac1, ac2 = st.columns(2)
                sel_qty        = ac1.number_input("Quantity", min_value=1,
                                                   max_value=max(1, remaining),
                                                   value=1, step=1)
                sel_sell_price = ac2.number_input(
                    "Selling Price (₦)",
                    min_value=0.0,
                    value=float(original_price),
                    step=500.0,
                    help="Defaults to listed price. Type negotiated amount if different."
                )
                if sel_sell_price > original_price:
                    st.warning(
                        f"⚠️ Above listed price ({fmt_naira(original_price)}). Confirm?"
                    )
                add_btn = st.form_submit_button(
                    "➕ Add to Cart", type="primary", use_container_width=True
                )

            if add_btn:
                prod_row   = in_stock[in_stock["product_name"] == sel_name].iloc[0]
                unit_price = safe_float(prod_row["selling_price"])
                cost_price = safe_float(prod_row["cost_price"])

                if sel_qty > remaining:
                    st.error(f"Only {remaining} units available for {sel_name}.")
                else:
                    negotiated_price = float(sel_sell_price)
                    disc_amt         = max(0, round((unit_price - negotiated_price) * sel_qty, 2))
                    line_total       = round(negotiated_price * sel_qty, 2)
                    cost_total       = round(cost_price * sel_qty, 2)

                    # Merge if same product + same negotiated price already in cart
                    merged = False
                    for item in st.session_state.cart:
                        if (item["product_id"] == prod_row["product_id"] and
                                item["negotiated_price"] == negotiated_price):
                            item["quantity"]     += int(sel_qty)
                            item["disc_amt"]      = max(0, round(
                                (unit_price - negotiated_price) * item["quantity"], 2))
                            item["line_total"]    = round(negotiated_price * item["quantity"], 2)
                            item["cost_total"]    = round(cost_price * item["quantity"], 2)
                            item["gross_profit"]  = round(
                                item["line_total"] - item["cost_total"], 2)
                            item["discount_amt"]  = item["disc_amt"]
                            merged = True
                            break

                    if not merged:
                        st.session_state.cart.append({
                            "product_id":       prod_row["product_id"],
                            "product_name":     sel_name,
                            "quantity":         int(sel_qty),
                            "unit_price":       unit_price,
                            "negotiated_price": negotiated_price,
                            "cost_price":       cost_price,
                            "discount_pct":     0.0,
                            "discount_amt":     disc_amt,
                            "line_total":       line_total,
                            "cost_total":       cost_total,
                            "gross_profit":     round(line_total - cost_total, 2),
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
                ic1, ic2 = st.columns([4, 1])
                with ic1:
                    negotiated = item.get("negotiated_price", item["unit_price"])
                    if negotiated < item["unit_price"]:
                        price_str = (
                            f"~~{fmt_naira(item['unit_price'])}~~ → "
                            f"**{fmt_naira(negotiated)}**"
                            f" (-{fmt_naira(item['discount_amt'])})"
                        )
                    else:
                        price_str = fmt_naira(item["unit_price"])
                    item_desc = (
                        f"**{item['product_name']}** × {item['quantity']} "
                        f"@ {price_str}  \n"
                        f"**Line total: {fmt_naira(item['line_total'])}**"
                    )
                    st.markdown(item_desc)
                with ic2:
                    if st.button("🗑️", key=f"rm_{idx}", help="Remove item"):
                        st.session_state.cart.pop(idx)
                        st.rerun()

                grand_total    += item["line_total"]
                total_discount += item["discount_amt"]
                total_cost     += item["cost_total"]
                total_profit   += item["gross_profit"]
                st.markdown("---")

            # Cart summary
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

    # ════════════════════════════════════
    #  RIGHT: Checkout + Today's sales
    # ════════════════════════════════════
    with col2:
        section_header("💳 Checkout")

        if st.session_state.cart:
            with st.form("checkout_form"):
                customer_name = st.text_input("Customer Name (optional)",
                                               placeholder="e.g. Emeka Obi")
                payment_method = st.selectbox(
                    "Payment Method",
                    ["Cash", "Bank Transfer", "POS", "Mobile Money"]
                )
                sale_note = st.text_input("Note (optional)",
                                          placeholder="e.g. Bulk order, VIP customer")
                confirm_sale = st.form_submit_button(
                    f"✅ Record Sale — {fmt_naira(sum(i['line_total'] for i in st.session_state.cart))}",
                    type="primary", use_container_width=True
                )

            if confirm_sale:
                sale_id    = gen_id("SL")
                sale_time  = datetime.now().isoformat()
                cart       = st.session_state.cart
                grand_total    = sum(i["line_total"]   for i in cart)
                total_discount = sum(i["discount_amt"] for i in cart)
                total_cost     = sum(i["cost_total"]   for i in cart)
                total_profit   = sum(i["gross_profit"] for i in cart)

                # ── Write sale header to sales table ──
                sale_ok = db_insert(TBL_SALES, {
                    "sale_id":        sale_id,
                    "business_id":    business_id,
                    "product_id":     cart[0]["product_id"],
                    "product_name":   ", ".join(i["product_name"] for i in cart),
                    "quantity":       sum(i["quantity"] for i in cart),
                    "unit_price":     cart[0]["unit_price"],
                    "total_amount":   grand_total,
                    "cost_total":     total_cost,
                    "gross_profit":   total_profit,
                    "payment_method": payment_method,
                    "sale_date":      sale_time,
                    "customer_name":  customer_name.strip(),
                    "discount_total": total_discount,
                    "item_count":     len(cart),
                })

                if sale_ok:
                    # ── Write each line item to sale_items ──
                    items_ok = True
                    for item in cart:
                        ok = db_insert(TBL_SALE_ITEMS, {
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
                        })
                        if not ok:
                            items_ok = False

                    # ── Deduct stock for all items ──
                    live_products = get_products_df(business_id)
                    for item in cart:
                        if not live_products.empty:
                            pr = live_products[live_products["product_id"] == item["product_id"]]
                            if not pr.empty:
                                new_stock = int(pr.iloc[0]["stock_quantity"]) - item["quantity"]
                                db_update(TBL_PRODUCTS, "product_id",
                                          item["product_id"],
                                          {"stock_quantity": max(0, new_stock)})

                    st.cache_data.clear()

                    # ── Store receipt data and clear cart ──
                    st.session_state.sale_done = {
                        "sale_id":       sale_id,
                        "sale_time":     sale_time,
                        "customer_name": customer_name.strip(),
                        "payment":       payment_method,
                        "note":          sale_note.strip(),
                        "items":         cart,
                        "grand_total":   grand_total,
                        "discount":      total_discount,
                        "profit":        total_profit,
                        "business_name": user.get("business_name", ""),
                    }
                    st.session_state.cart = []
                    st.rerun()
                else:
                    st.error("Failed to record sale. Please try again.")

            if st.button("🗑️ Clear Cart", use_container_width=True):
                st.session_state.cart = []
                st.session_state.sale_done = None
                st.rerun()
        else:
            st.info("Add items to the cart to checkout.")

        # ── Receipt display ──
        if st.session_state.get("sale_done"):
            rd = st.session_state.sale_done
            st.markdown("---")
            section_header("🧾 Receipt")

            receipt_lines = []
            receipt_lines.append(f"{'='*38}")
            receipt_lines.append(f"  {rd['business_name'].upper()}")
            receipt_lines.append(f"  {datetime.fromisoformat(rd['sale_time']).strftime('%d %b %Y  %H:%M')}")
            receipt_lines.append(f"  Sale ID: {rd['sale_id']}")
            if rd["customer_name"]:
                receipt_lines.append(f"  Customer: {rd['customer_name']}")
            receipt_lines.append(f"{'='*38}")
            for item in rd["items"]:
                negotiated = item.get("negotiated_price", item["unit_price"])
                receipt_lines.append(
                    f"  {item['product_name'][:20]:<20}"
                )
                receipt_lines.append(
                    f"  {item['quantity']} x {fmt_naira(negotiated)}"
                    f" = {fmt_naira(item['line_total'])}"
                )
            receipt_lines.append(f"{'-'*38}")
            receipt_lines.append(f"  TOTAL:  {fmt_naira(rd['grand_total'])}")
            receipt_lines.append(f"  Payment: {rd['payment']}")
            if rd["note"]:
                receipt_lines.append(f"  Note: {rd['note']}")
            receipt_lines.append(f"{'='*38}")
            receipt_lines.append(f"  Thank you for your purchase!")
            receipt_lines.append(f"{'='*38}")

            receipt_text = "\n".join(receipt_lines)

            st.code(receipt_text, language=None)

            # ── PDF Receipt ──
            try:
                from reportlab.lib.pagesizes import A6
                from reportlab.lib import colors
                from reportlab.lib.units import mm
                from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                                Spacer, HRFlowable, Table, TableStyle)
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
                import io

                buf = io.BytesIO()
                doc = SimpleDocTemplate(
                    buf, pagesize=A6,
                    leftMargin=10*mm, rightMargin=10*mm,
                    topMargin=8*mm,  bottomMargin=8*mm
                )
                styles = getSampleStyleSheet()
                bold_center = ParagraphStyle("bc", parent=styles["Normal"],
                                             fontName="Helvetica-Bold",
                                             fontSize=11, alignment=TA_CENTER,
                                             spaceAfter=2)
                normal_c    = ParagraphStyle("nc", parent=styles["Normal"],
                                             fontSize=8, alignment=TA_CENTER,
                                             spaceAfter=1)
                normal_l    = ParagraphStyle("nl", parent=styles["Normal"],
                                             fontSize=8, alignment=TA_LEFT,
                                             spaceAfter=1)
                small_r     = ParagraphStyle("sr", parent=styles["Normal"],
                                             fontSize=8, alignment=TA_RIGHT)

                story = []
                story.append(Paragraph(rd["business_name"].upper(), bold_center))
                story.append(Paragraph(
                    datetime.fromisoformat(rd["sale_time"]).strftime("%d %b %Y  %H:%M"),
                    normal_c))
                story.append(Paragraph(f"Sale ID: {rd['sale_id']}", normal_c))
                if rd["customer_name"]:
                    story.append(Paragraph(f"Customer: {rd['customer_name']}", normal_c))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
                story.append(Spacer(1, 3*mm))

                # Items table — show only what customer paid
                tdata = [["Item", "Qty", "Price", "Total"]]
                for item in rd["items"]:
                    negotiated = item.get("negotiated_price", item["unit_price"])
                    tdata.append([
                        item["product_name"][:18],
                        str(item["quantity"]),
                        f"\u20a6{negotiated:,.0f}",
                        f"\u20a6{item['line_total']:,.0f}",
                    ])

                col_w = [45*mm, 10*mm, 22*mm, 22*mm]
                t = Table(tdata, colWidths=col_w)
                t.setStyle(TableStyle([
                    ("FONTNAME",  (0,0), (-1,0),  "Helvetica-Bold"),
                    ("FONTSIZE",  (0,0), (-1,-1),  8),
                    ("ALIGN",     (1,0), (-1,-1),  "RIGHT"),
                    ("LINEBELOW", (0,0), (-1,0),   0.5, colors.black),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1),
                     [colors.white, colors.Color(0.95,0.95,0.95)]),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ]))
                story.append(t)
                story.append(Spacer(1, 3*mm))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))

                story.append(Paragraph(
                    f"<b>TOTAL: \u20a6{rd['grand_total']:,.0f}</b>", bold_center))
                story.append(Paragraph(f"Payment: {rd['payment']}", normal_c))
                if rd["note"]:
                    story.append(Paragraph(f"Note: {rd['note']}", normal_c))
                story.append(Spacer(1, 4*mm))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
                story.append(Paragraph("Thank you for your purchase!", normal_c))

                doc.build(story)
                pdf_bytes = buf.getvalue()

                fname = (f"receipt_{rd['sale_id']}_"
                         f"{datetime.fromisoformat(rd['sale_time']).strftime('%Y%m%d_%H%M')}.pdf")

                st.download_button(
                    label="📄 Download PDF Receipt",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                )

                # WhatsApp share link
                wa_text = (
                    f"Receipt from {rd['business_name']}\n"
                    f"Date: {datetime.fromisoformat(rd['sale_time']).strftime('%d %b %Y %H:%M')}\n"
                    f"Items: {', '.join(f"{i['product_name']} x{i['quantity']}" for i in rd['items'])}\n"
                    f"Total: \u20a6{rd['grand_total']:,.0f}\n"
                    f"Payment: {rd['payment']}\n"
                    f"Thank you!"
                )
                import urllib.parse
                wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"
                st.markdown(
                    f"""<a href="{wa_url}" target="_blank"
                        style="display:block;text-align:center;background:#25D366;
                               color:white;padding:0.6rem;border-radius:8px;
                               font-weight:600;text-decoration:none;margin-top:0.5rem;">
                        💬 Share via WhatsApp
                    </a>""",
                    unsafe_allow_html=True
                )

            except ImportError:
                st.warning("Install reportlab for PDF receipts: pip install reportlab")



    # ── Today's Sales (outside col2, always visible) ──
    st.markdown('---')
    section_header("Today's Sales")
    try:
        sales_df_today = get_sales_df(business_id)
        if not sales_df_today.empty:
            sales_df_today['sale_date'] = pd.to_datetime(
                sales_df_today['sale_date'], errors='coerce', utc=True
            ).dt.tz_localize(None)
            sales_df_today = sales_df_today.dropna(subset=['sale_date'])
            today       = datetime.now().date()
            today_sales = sales_df_today[sales_df_today['sale_date'].dt.date == today]
            kpi_card("Today's Revenue",
                     fmt_naira(today_sales['total_amount'].sum()),
                     f"{len(today_sales)} transactions today")
            if not today_sales.empty:
                st.markdown('**Recent transactions:**')
                recent = today_sales.sort_values('sale_date', ascending=False).head(5)
                for _, r in recent.iterrows():
                    st.markdown(
                        f"• **{r['product_name']}** "
                        f"= {fmt_naira(r['total_amount'])} _{r['payment_method']}_"
                    )
        else:
            kpi_card("Today's Revenue", "₦0.00", "No sales yet today")
    except Exception:
        st.info('No sales data yet.')

