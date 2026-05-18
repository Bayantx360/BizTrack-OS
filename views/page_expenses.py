# ============================================================
#  pages/page_expenses.py
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


def page_expenses():
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("💸 Expense Tracker", "Log and monitor your business expenses")

    tab1, tab2 = st.tabs(["📋 View Expenses", "➕ Log Expense"])

    with tab1:
        expenses_df = get_expenses_df(business_id)
        if expenses_df.empty:
            st.info("No expenses logged yet.")
        else:
            # Date filter
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
                         f"In selected period")
            with c2:
                kpi_card("Transactions", str(len(filtered)), "Expense entries")
            with c3:
                avg = filtered["amount"].mean() if not filtered.empty else 0
                kpi_card("Average Expense", fmt_naira(avg), "Per entry")

            if not filtered.empty:
                # Category breakdown chart
                cat_breakdown = (
                    filtered.groupby("category")["amount"]
                    .sum().reset_index()
                    .sort_values("amount", ascending=False)
                )
                if not cat_breakdown.empty:
                    fig = px.bar(
                        cat_breakdown, x="category", y="amount",
                        labels={"amount": "Amount (₦)", "category": "Category"},
                        color_discrete_sequence=["#ef4444"],
                        title="Expenses by Category"
                    )
                    fig.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=40, b=0),
                        height=280,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Search
                exp_search = st.text_input("🔍 Search expenses", key="exp_search", placeholder="Filter by description…")
                if exp_search:
                    filtered = filtered[filtered["expense_name"].str.contains(exp_search, case=False, na=False)]

                # Pagination
                EXP_PAGE_SIZE = 20
                exp_total_pages = max(1, -(-len(filtered) // EXP_PAGE_SIZE))
                if "exp_page" not in st.session_state:
                    st.session_state.exp_page = 1
                exp_pg = st.session_state.exp_page
                filtered_sorted = filtered.sort_values("expense_date", ascending=False)
                exp_page_df = filtered_sorted.iloc[(exp_pg - 1) * EXP_PAGE_SIZE: exp_pg * EXP_PAGE_SIZE]

                st.caption(f"Showing {len(exp_page_df)} of {len(filtered)} entries  •  Page {exp_pg} of {exp_total_pages}")
                st.markdown("---")

                # Editable rows
                for _, r in exp_page_df.iterrows():
                    exp_id = r["expense_id"]
                    edit_key = f"exp_edit_{exp_id}"
                    with st.expander(
                        f"**{r['expense_name']}** | {r['category']} | "
                        f"{fmt_naira(r['amount'])} | {r['expense_date'].strftime('%d %b %Y') if pd.notna(r['expense_date']) else ''}",
                        expanded=False
                    ):
                        with st.form(f"edit_exp_{exp_id}"):
                            ef1, ef2 = st.columns(2)
                            new_exp_name = ef1.text_input("Description", value=r["expense_name"])
                            new_exp_cat  = ef2.selectbox("Category", [
                                "Rent","Utilities","Salaries","Supplies","Transport",
                                "Marketing","Maintenance","Taxes","Miscellaneous"
                            ], index=["Rent","Utilities","Salaries","Supplies","Transport",
                                      "Marketing","Maintenance","Taxes","Miscellaneous"].index(r["category"])
                                if r["category"] in ["Rent","Utilities","Salaries","Supplies","Transport",
                                                     "Marketing","Maintenance","Taxes","Miscellaneous"] else 0)
                            new_exp_amt  = ef1.number_input("Amount (₦)", value=safe_float(r["amount"]), min_value=0.0, step=100.0)
                            new_exp_date = ef2.date_input("Date", value=r["expense_date"].date() if pd.notna(r["expense_date"]) else datetime.now().date())
                            save_exp = st.form_submit_button("💾 Save Changes", type="primary")

                        if save_exp:
                            ok = db_update(TBL_EXPENSES, "expense_id", exp_id, {
                                "expense_name": new_exp_name.strip(),
                                "category":     new_exp_cat,
                                "amount":       new_exp_amt,
                                "expense_date": str(new_exp_date),
                            })
                            st.cache_data.clear()
                            st.session_state[f"exp_msg_{exp_id}"] = (
                                "✅ Expense updated successfully."
                                if ok else "❌ Failed to update expense. Please try again."
                            )
                            st.rerun()

                        # Show feedback message
                        exp_msg_key = f"exp_msg_{exp_id}"
                        if exp_msg_key in st.session_state:
                            msg = st.session_state.pop(exp_msg_key)
                            if msg.startswith("✅"):
                                st.success(msg)
                            else:
                                st.error(msg)

                        # Delete with confirmation
                        confirm_exp_key = f"confirm_del_exp_{exp_id}"
                        if not st.session_state.get(confirm_exp_key, False):
                            if st.button("🗑️ Delete this expense", key=f"del_exp_{exp_id}"):
                                st.session_state[confirm_exp_key] = True
                                st.rerun()
                        else:
                            st.warning("⚠️ Delete this expense entry permanently?")
                            ce1, ce2 = st.columns(2)
                            if ce1.button("✅ Yes, delete", key=f"yes_del_exp_{exp_id}", type="primary"):
                                ok = db_delete(TBL_EXPENSES, "expense_id", exp_id)
                                st.cache_data.clear()
                                st.session_state.pop(confirm_exp_key, None)
                                st.session_state["exp_del_msg"] = (
                                    "✅ Expense deleted." if ok else "❌ Failed to delete expense."
                                )
                                st.rerun()
                            if ce2.button("❌ Cancel", key=f"no_del_exp_{exp_id}"):
                                st.session_state.pop(confirm_exp_key, None)
                                st.rerun()

                        if "exp_del_msg" in st.session_state:
                            msg = st.session_state.pop("exp_del_msg")
                            if msg.startswith("✅"):
                                st.success(msg)
                            else:
                                st.error(msg)

                # Pagination controls
                if exp_total_pages > 1:
                    st.markdown("---")
                    ep1, ep2, ep3 = st.columns([1, 3, 1])
                    if ep1.button("◀ Prev", disabled=(exp_pg <= 1), key="exp_prev"):
                        st.session_state.exp_page = max(1, exp_pg - 1)
                        st.rerun()
                    ep2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {exp_pg} of {exp_total_pages}</div>", unsafe_allow_html=True)
                    if ep3.button("Next ▶", disabled=(exp_pg >= exp_total_pages), key="exp_next"):
                        st.session_state.exp_page = min(exp_total_pages, exp_pg + 1)
                        st.rerun()

    with tab2:
        with st.form("log_expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            exp_name = col1.text_input("Description *", placeholder="e.g. Generator fuel")
            category = col2.selectbox("Category", [
                "Rent", "Utilities", "Salaries", "Supplies", "Transport",
                "Marketing", "Maintenance", "Taxes", "Miscellaneous"
            ])
            amount      = col1.number_input("Amount (₦) *", min_value=0.0, step=100.0)
            expense_date = col2.date_input("Date", value=datetime.now().date())
            submitted = st.form_submit_button("Log Expense", use_container_width=True, type="primary")

        if submitted:
            if not exp_name or amount <= 0:
                st.error("Please fill in description and a valid amount.")
            else:
                expense_id = gen_id("EXP")
                ok = db_insert(TBL_EXPENSES, {
                    "expense_id":   expense_id,
                    "business_id":  business_id,
                    "expense_name": exp_name.strip(),
                    "category":     category,
                    "amount":       amount,
                    "expense_date": str(expense_date),
                    "recorded_by":  user.get("full_name", user.get("email", "")),
                })
                if ok:
                    st.success(f"✅ Expense logged: {exp_name} — {fmt_naira(amount)}")
                    st.rerun()
                else:
                    st.error("Failed to log expense.")


# ─────────────────────────────────────────────
#  PAGE: BUSINESS INSIGHTS
# ─────────────────────────────────────────────

