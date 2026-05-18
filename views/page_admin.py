# ============================================================
#  pages/page_admin.py
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


def page_admin():
    page_header("🛡️ Admin Panel", "BizPulse platform management")

    users_df = db_fetch(TBL_USERS)

    if users_df.empty:
        st.info("No users found.")
        return

    # Platform stats
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Businesses", str(len(users_df)), "Registered accounts")
    with c2:
        active = len(users_df[users_df["plan_status"] == "active"])
        kpi_card("Active Subscriptions", str(active), "Paying or trial users")
    with c3:
        pending = len(users_df[users_df["plan_status"] == "pending_payment"])
        kpi_card("Pending Payment", str(pending), "Awaiting manual activation")
    with c4:
        monthly_rev = len(users_df[
            (users_df["plan_type"] == "monthly") &
            (users_df["plan_status"] == "active")
        ]) * PAYMENT_DETAILS["monthly_price"]
        yearly_rev = len(users_df[
            (users_df["plan_type"] == "yearly") &
            (users_df["plan_status"] == "active")
        ]) * (PAYMENT_DETAILS["yearly_price"] / 12)  # normalise yearly to monthly
        kpi_card("Est. MRR",
                 fmt_naira(monthly_rev + yearly_rev), "From active paid plans")

    # ── Real revenue KPIs from PAYMENTS ledger ──
    payments_df = get_payments_df()
    if not payments_df.empty:
        now_dt      = datetime.now()
        month_start = datetime(now_dt.year, now_dt.month, 1)
        year_start  = datetime(now_dt.year, 1, 1)

        total_collected      = payments_df["amount"].sum()
        month_collected      = payments_df[
            payments_df["payment_date"] >= month_start
        ]["amount"].sum()
        year_collected       = payments_df[
            payments_df["payment_date"] >= year_start
        ]["amount"].sum()
        total_transactions   = len(payments_df)

        st.markdown("---")
        st.markdown("#### 💰 Platform Revenue — Actual Collected")
        r1, r2, r3, r4 = st.columns(4)
        with r1:
            kpi_card("All-Time Revenue", fmt_naira(total_collected),
                     f"{total_transactions} payments received")
        with r2:
            kpi_card("This Month", fmt_naira(month_collected),
                     now_dt.strftime("%B %Y"))
        with r3:
            kpi_card("This Year", fmt_naira(year_collected),
                     str(now_dt.year))
        with r4:
            avg_per_payment = total_collected / total_transactions if total_transactions else 0
            kpi_card("Avg. per Payment", fmt_naira(avg_per_payment),
                     "Across all activations & renewals")
    else:
        st.info("💡 No payment records yet. Revenue will appear here as you activate users.")

    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "⏳ Pending Activation",
        "✅ Active Users",
        "📈 MRR & Growth",
        "🚨 Churn Alerts",
        "🔑 Password Resets",
        "👥 All Users",
        "⛔ Deactivated",
    ])

    # ── Pending ──
    with tab1:
        pending_df = users_df[users_df["plan_status"] == "pending_payment"]
        if pending_df.empty:
            st.success("No pending activations.")
        else:
            for _, u in pending_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                        st.caption(f"📧 {u['email']} | Plan: {u['plan_type']} | Signed up: {u['created_at']}")
                    with col2:
                        plan   = u["plan_type"]
                        days   = 30 if plan == "monthly" else 365
                        end_dt = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                        if st.button(f"✅ Activate", key=f"act_{u['user_id']}"):
                            ok = db_update(TBL_USERS, "user_id", u["user_id"], {
                                    "plan_status":       "active",
                                    "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                                    "subscription_end":   end_dt,
                                })
                            if ok:
                                pay_amount = (PAYMENT_DETAILS["yearly_price"]
                                              if plan == "yearly"
                                              else PAYMENT_DETAILS["monthly_price"])
                                log_payment(
                                    u["user_id"], u["business_name"], u["email"],
                                    plan, pay_amount, "Initial activation"
                                )
                                st.cache_data.clear()
                                st.success(f"✅ {u['business_name']} activated until {end_dt}")
                                st.rerun()
                    with col3:
                        confirm_del_key = f"confirm_del_user_{u['user_id']}"
                        if not st.session_state.get(confirm_del_key, False):
                            if st.button("🗑️ Delete", key=f"del_u_{u['user_id']}"):
                                st.session_state[confirm_del_key] = True
                                st.rerun()
                        else:
                            st.warning("Delete this user?")
                            if st.button("✅ Confirm", key=f"confirm_yes_u_{u['user_id']}", type="primary"):
                                db_delete(TBL_USERS, "user_id", u["user_id"])
                                st.session_state.pop(confirm_del_key, None)
                                st.rerun()
                            if st.button("❌ Cancel", key=f"confirm_no_u_{u['user_id']}"):
                                st.session_state.pop(confirm_del_key, None)
                                st.rerun()
                    st.markdown("---")

    # ── Active ──
    with tab2:
        active_df = users_df[users_df["plan_status"] == "active"]
        if active_df.empty:
            st.info("No active users.")
        else:
            for _, u in active_df.iterrows():
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                    st.caption(f"📧 {u['email']} | {u['plan_type']} | Expires: {u.get('subscription_end','?')}")
                with col2:
                    ext_days  = 365 if u.get("plan_type") == "yearly" else 30
                    ext_label = "1 year" if ext_days == 365 else "30 days"
                    if st.button(f"🔁 Renew ({ext_label})", key=f"ext_{u['user_id']}"):
                        curr_end = parse_date(u.get("subscription_end", ""))
                        base     = curr_end if (curr_end and curr_end > datetime.now()) else datetime.now()
                        new_end  = (base + timedelta(days=ext_days)).strftime("%Y-%m-%d")
                        db_update(TBL_USERS, "user_id", u["user_id"], {"subscription_end": new_end})
                        pay_amount = (PAYMENT_DETAILS["yearly_price"]
                                      if ext_days == 365
                                      else PAYMENT_DETAILS["monthly_price"])
                        log_payment(
                            u["user_id"], u["business_name"], u["email"],
                            u.get("plan_type", "monthly"), pay_amount, "Renewal"
                        )
                        st.cache_data.clear()
                        st.success(f"✅ Renewed to {new_end}")
                        st.rerun()
                with col3:
                    if st.button("⛔ Deactivate", key=f"deact_{u['user_id']}"):
                        db_update(TBL_USERS, "user_id", u["user_id"], {"plan_status": "expired"})
                        st.rerun()
                st.markdown("---")

    # ── MRR & Growth ──
    with tab3:
        st.markdown("### 📈 Monthly Recurring Revenue")

        # ── Real collected revenue section (from PAYMENTS ledger) ──
        payments_df = get_payments_df()
        if not payments_df.empty:
            st.markdown("#### 💰 Actual Collected Revenue by Month")
            pay_chart = payments_df.copy()
            pay_chart["month"] = pay_chart["payment_date"].dt.to_period("M")
            monthly_collected = (
                pay_chart.groupby("month")
                .agg(collected=("amount", "sum"), count=("amount", "count"))
                .reset_index()
            )
            monthly_collected["month_str"] = monthly_collected["month"].dt.strftime("%b %Y")

            fig_collected = go.Figure()
            fig_collected.add_trace(go.Bar(
                x=monthly_collected["month_str"],
                y=monthly_collected["collected"],
                name="Collected",
                marker_color="#10b981",
                text=[fmt_naira(v) for v in monthly_collected["collected"]],
                textposition="outside",
            ))
            fig_collected.update_layout(
                title="Cash Collected per Month",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(tickprefix="₦", gridcolor="#f1f5f9"),
                margin=dict(l=0, r=0, t=40, b=0),
                height=300,
                showlegend=False,
            )
            st.plotly_chart(fig_collected, use_container_width=True)

            # Plan type breakdown
            plan_totals = (
                pay_chart.groupby("plan_type")["amount"]
                .sum().reset_index()
                .rename(columns={"amount": "total"})
            )
            col_l, col_r = st.columns(2)
            with col_l:
                fig_pie = px.pie(
                    plan_totals, values="total", names="plan_type",
                    title="Revenue by Plan Type",
                    color_discrete_sequence=["#6366f1", "#10b981", "#f59e0b"],
                    hole=0.45,
                )
                fig_pie.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=280,
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            with col_r:
                st.markdown("**Payment breakdown**")
                for _, row in plan_totals.iterrows():
                    pct = row["total"] / payments_df["amount"].sum() * 100
                    st.markdown(
                        f"**{row['plan_type'].capitalize()}** — "
                        f"{fmt_naira(row['total'])} ({pct:.1f}%)"
                    )
                st.markdown("---")
                st.markdown(f"**Total payments received:** {len(payments_df)}")
                st.markdown(
                    f"**Latest payment:** "
                    f"{payments_df['payment_date'].max().strftime('%d %b %Y')}"
                )

            st.markdown("---")
            with st.expander("📋 Full payment ledger"):
                show = payments_df[[c for c in
                    ["payment_id","business_name","email","plan_type",
                     "amount","payment_date","note"]
                    if c in payments_df.columns
                ]].sort_values("payment_date", ascending=False)
                st.dataframe(show, use_container_width=True)
                csv = show.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Export Payment Ledger CSV", data=csv,
                    file_name="bizpulse_payments.csv", mime="text/csv",
                )
            st.markdown("---")
        else:
            st.info("💡 No payment records yet. They'll appear here as you activate users.")
            st.markdown("---")

        st.markdown("#### 📊 Estimated MRR (Active Users)")

        # Build a month-by-month activation history from created_at + plan_type
        import calendar

        paid_df = users_df[
            (users_df["plan_status"].isin(["active", "expired"])) &
            (users_df["plan_type"].isin(["monthly", "yearly"]))
        ].copy()

        if paid_df.empty:
            st.info("No paid user data yet. MRR chart will appear once users activate.")
        else:
            # Parse activation dates
            paid_df["activation_date"] = pd.to_datetime(
                paid_df["subscription_start"], errors="coerce", utc=True
            ).dt.tz_localize(None)
            paid_df = paid_df.dropna(subset=["activation_date"])

            if paid_df.empty:
                st.info("No activation dates found. Activate users to start tracking MRR.")
            else:
                # Build monthly cohort: for each calendar month, count active paid users
                # and their contribution to MRR
                min_month = paid_df["activation_date"].dt.to_period("M").min()
                max_month = pd.Timestamp.now().to_period("M")
                periods   = pd.period_range(min_month, max_month, freq="M")

                mrr_rows = []
                for period in periods:
                    period_end = pd.Timestamp(period.to_timestamp("M"))
                    # User is "active" in this month if activated on or before month end
                    # and subscription_end is after month start
                    month_start = pd.Timestamp(period.to_timestamp())
                    active_mask = paid_df["activation_date"] <= period_end
                    # Check subscription_end if available
                    if "subscription_end" in paid_df.columns:
                        sub_end = pd.to_datetime(paid_df["subscription_end"], errors="coerce", utc=True).dt.tz_localize(None)
                        active_mask = active_mask & (
                            sub_end.isna() | (sub_end >= month_start)
                        )
                    cohort   = paid_df[active_mask]
                    monthly_c = len(cohort[cohort["plan_type"] == "monthly"])
                    yearly_c  = len(cohort[cohort["plan_type"] == "yearly"])
                    mrr       = (monthly_c * PAYMENT_DETAILS["monthly_price"] +
                                 yearly_c  * (PAYMENT_DETAILS["yearly_price"] / 12))
                    mrr_rows.append({
                        "month":   period.strftime("%b %Y"),
                        "mrr":     mrr,
                        "monthly": monthly_c,
                        "yearly":  yearly_c,
                        "total":   monthly_c + yearly_c,
                    })

                mrr_df = pd.DataFrame(mrr_rows)

                # ── KPIs ──
                current_mrr  = mrr_df["mrr"].iloc[-1]  if not mrr_df.empty else 0
                previous_mrr = mrr_df["mrr"].iloc[-2]  if len(mrr_df) > 1  else 0
                arr          = current_mrr * 12
                mrr_growth   = ((current_mrr - previous_mrr) / previous_mrr * 100
                                if previous_mrr > 0 else 0)

                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    kpi_card("Current MRR", fmt_naira(current_mrr),
                             "This month's recurring revenue")
                with k2:
                    kpi_card("ARR (projected)", fmt_naira(arr),
                             "MRR × 12")
                with k3:
                    direction = "▲" if mrr_growth >= 0 else "▼"
                    kpi_card("MRR Growth", f"{direction} {abs(mrr_growth):.1f}%",
                             "vs last month", positive=(mrr_growth >= 0))
                with k4:
                    kpi_card("Paid Users", str(int(mrr_df["total"].iloc[-1])),
                             f"{int(mrr_df['monthly'].iloc[-1])} monthly · "
                             f"{int(mrr_df['yearly'].iloc[-1])} yearly")

                st.markdown("---")

                # ── MRR Bar Chart ──
                fig_mrr = go.Figure()
                fig_mrr.add_trace(go.Bar(
                    x=mrr_df["month"], y=mrr_df["mrr"],
                    name="MRR",
                    marker_color="#6366f1",
                    text=[fmt_naira(v) for v in mrr_df["mrr"]],
                    textposition="outside",
                ))
                fig_mrr.update_layout(
                    title="Monthly Recurring Revenue",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(tickprefix="₦", gridcolor="#f1f5f9"),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=350,
                    showlegend=False,
                )
                st.plotly_chart(fig_mrr, use_container_width=True)

                # ── User count stacked bar ──
                fig_users = go.Figure()
                fig_users.add_trace(go.Bar(
                    x=mrr_df["month"], y=mrr_df["monthly"],
                    name="Monthly plan", marker_color="#6366f1",
                ))
                fig_users.add_trace(go.Bar(
                    x=mrr_df["month"], y=mrr_df["yearly"],
                    name="Yearly plan", marker_color="#10b981",
                ))
                fig_users.update_layout(
                    title="Active Paid Users by Plan",
                    barmode="stack",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(gridcolor="#f1f5f9"),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=300,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig_users, use_container_width=True)

    # ── Churn Alerts ──
    with tab4:
        st.markdown("### 🚨 Churn Alerts")
        st.caption(
            "Users whose subscription expires within 7 days. "
            "Reach out before they lapse."
        )

        if "subscription_end" not in users_df.columns:
            st.info("No subscription data available.")
        else:
            now      = datetime.now()
            soon     = now + timedelta(days=7)
            active_u = users_df[users_df["plan_status"] == "active"].copy()

            if active_u.empty:
                st.info("No active users yet.")
            else:
                active_u["sub_end_dt"] = pd.to_datetime(
                    active_u["subscription_end"], errors="coerce", utc=True
                ).dt.tz_localize(None)
                expiring = active_u[
                    (active_u["sub_end_dt"] >= pd.Timestamp(now)) &
                    (active_u["sub_end_dt"] <= pd.Timestamp(soon))
                ].sort_values("sub_end_dt")

                already_expired = users_df[
                    users_df["plan_status"] == "expired"
                ].copy()

                # ── Summary KPIs ──
                k1, k2, k3 = st.columns(3)
                with k1:
                    kpi_card("Expiring in 7 days", str(len(expiring)),
                             "Need immediate attention", positive=(len(expiring) == 0))
                with k2:
                    kpi_card("Already Expired", str(len(already_expired)),
                             "Lapsed — potential win-back")
                with k3:
                    trial_u = users_df[
                        (users_df["plan_type"] == "trial") &
                        (users_df["plan_status"] == "active")
                    ]
                    kpi_card("Active Trials", str(len(trial_u)),
                             "Potential conversions")

                st.markdown("---")

                # ── Expiring soon list ──
                st.markdown("#### ⏰ Expiring within 7 days")
                if expiring.empty:
                    st.success("✅ No subscriptions expiring in the next 7 days.")
                else:
                    for _, u in expiring.iterrows():
                        days_left = (u["sub_end_dt"] - pd.Timestamp(now)).days
                        color     = "#ef4444" if days_left <= 2 else "#f59e0b"
                        with st.container(border=True):
                            col1, col2, col3 = st.columns([3, 2, 2])
                            with col1:
                                st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                                st.caption(f"📧 {u['email']} | {u['plan_type'].capitalize()} plan")
                            with col2:
                                st.markdown(
                                    f"<span style='color:{color};font-weight:700;'>"
                                    f"⏳ {days_left} day{'s' if days_left != 1 else ''} left</span>"
                                    f"<br><small style='color:#64748b;'>"
                                    f"Expires {u['sub_end_dt'].strftime('%d %b %Y')}</small>",
                                    unsafe_allow_html=True,
                                )
                            with col3:
                                ext_days  = 365 if u.get("plan_type") == "yearly" else 30
                                ext_label = "1 year" if ext_days == 365 else "30 days"
                                if st.button(f"🔁 Renew ({ext_label})",
                                             key=f"churn_ext_{u['user_id']}"):
                                    base    = u["sub_end_dt"] if u["sub_end_dt"] > pd.Timestamp(now) else pd.Timestamp(now)
                                    new_end = (base + timedelta(days=ext_days)).strftime("%Y-%m-%d")
                                    db_update(TBL_USERS, "user_id", u["user_id"], {"subscription_end": new_end})
                                    pay_amount = (PAYMENT_DETAILS["yearly_price"]
                                                  if ext_days == 365
                                                  else PAYMENT_DETAILS["monthly_price"])
                                    log_payment(
                                        u["user_id"], u["business_name"], u["email"],
                                        u.get("plan_type", "monthly"), pay_amount,
                                        "Renewal — churn prevention"
                                    )
                                    st.cache_data.clear()
                                    st.success(f"✅ Renewed to {new_end}")
                                    st.rerun()

                # ── Trial users expiring ──
                st.markdown("---")
                st.markdown("#### 🎁 Trials expiring within 7 days")
                trial_expiring = active_u[
                    (active_u["plan_type"] == "trial") &
                    (active_u["sub_end_dt"] >= pd.Timestamp(now)) &
                    (active_u["sub_end_dt"] <= pd.Timestamp(soon))
                ].sort_values("sub_end_dt")

                if trial_expiring.empty:
                    st.success("✅ No trials expiring soon.")
                else:
                    st.info(f"{len(trial_expiring)} trial(s) ending soon — "
                            "good time to reach out and convert them.")
                    for _, u in trial_expiring.iterrows():
                        days_left = (u["sub_end_dt"] - pd.Timestamp(now)).days
                        with st.container(border=True):
                            col1, col2 = st.columns([4, 2])
                            with col1:
                                st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                                st.caption(
                                    f"📧 {u['email']} | "
                                    f"Trial ends in {days_left} day{'s' if days_left != 1 else ''} "
                                    f"({u['sub_end_dt'].strftime('%d %b %Y')})"
                                )
                            with col2:
                                st.caption("Send them your Flutterwave link to convert.")

                # ── Recently expired (win-back) ──
                st.markdown("---")
                st.markdown("#### 💔 Recently expired (last 30 days)")
                if already_expired.empty:
                    st.success("✅ No expired users.")
                else:
                    already_expired["sub_end_dt"] = pd.to_datetime(
                        already_expired["subscription_end"], errors="coerce", utc=True
                    ).dt.tz_localize(None)
                    recent_expired = already_expired[
                        already_expired["sub_end_dt"] >= pd.Timestamp(now - timedelta(days=30))
                    ].sort_values("sub_end_dt", ascending=False)

                    if recent_expired.empty:
                        st.success("✅ No users expired in the last 30 days.")
                    else:
                        st.warning(f"{len(recent_expired)} user(s) lapsed recently — "
                                   "consider a win-back message.")
                        for _, u in recent_expired.iterrows():
                            with st.container(border=True):
                                col1, col2, col3 = st.columns([3, 2, 2])
                                with col1:
                                    st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                                    st.caption(
                                        f"📧 {u['email']} | {u.get('plan_type','').capitalize()} | "
                                        f"Expired: {u['sub_end_dt'].strftime('%d %b %Y') if pd.notna(u['sub_end_dt']) else 'unknown'}"
                                    )
                                with col2:
                                    ext_days  = 365 if u.get("plan_type") == "yearly" else 30
                                    ext_label = "1 year" if ext_days == 365 else "30 days"
                                    if st.button(f"🔁 Reactivate ({ext_label})",
                                                 key=f"react_{u['user_id']}"):
                                        new_end = (datetime.now() + timedelta(days=ext_days)).strftime("%Y-%m-%d")
                                        db_update(TBL_USERS, "user_id", u["user_id"], {
                                                "plan_status":      "active",
                                                "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                                                "subscription_end": new_end,
                                            })
                                        pay_amount = (PAYMENT_DETAILS["yearly_price"]
                                                      if ext_days == 365
                                                      else PAYMENT_DETAILS["monthly_price"])
                                        log_payment(
                                            u["user_id"], u["business_name"], u["email"],
                                            u.get("plan_type", "monthly"), pay_amount,
                                            "Reactivation — win-back"
                                        )
                                        st.cache_data.clear()
                                        st.success(f"✅ Reactivated until {new_end}")
                                        st.rerun()
                                with col3:
                                    st.caption("📤 Send Flutterwave link to renew")

    # ── Password Resets ──
    with tab5:
        if "password_reset_requested" not in users_df.columns:
            st.info("No password reset requests yet.")
        else:
            reset_df = users_df[users_df["password_reset_requested"] == "yes"]
            if reset_df.empty:
                st.success("✅ No pending password reset requests.")
            else:
                st.warning(f"{len(reset_df)} pending reset request(s)")
                for _, u in reset_df.iterrows():
                    with st.container():
                        col1, col2, col3 = st.columns([3, 2, 2])
                        with col1:
                            st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                            st.caption(
                                f"📧 {u['email']} | "
                                f"Requested: {u.get('reset_requested_at', 'unknown')}"
                            )
                        with col2:
                            btn_key  = f"genpw_{u['user_id']}"
                            show_key = f"show_temp_{u['user_id']}"

                            if st.button("🔑 Generate Temp Password", key=btn_key):
                                # Generate a cryptographically random 10-char password
                                # Admin never types it — system creates it and shows it once
                                alphabet = string.ascii_letters + string.digits + "!@#$"
                                temp_pw  = "".join(secrets.choice(alphabet) for _ in range(10))
                                hashed   = bcrypt.hashpw(
                                    temp_pw.encode(), bcrypt.gensalt()
                                ).decode()
                                ok = db_update(TBL_USERS, "user_id", u["user_id"], {
                                        "password_hash":            hashed,
                                        "password_reset_requested": "no",
                                        "reset_requested_at":       None,
                                        "must_change_password":     "yes",
                                    })
                                st.cache_data.clear()
                                if ok:
                                    # Store in session_state so it survives the rerun
                                    st.session_state[show_key] = temp_pw

                            # Show temp password if just generated — copy and send to user
                            if show_key in st.session_state:
                                st.success("✅ Password generated! Send this to the user:")
                                st.code(st.session_state[show_key], language=None)
                                st.caption(
                                    "⚠️ Copy it now — it won't be shown again. "
                                    "The user will be forced to change it on first login."
                                )
                                if st.button("✔ Done — clear", key=f"clear_{u['user_id']}"):
                                    del st.session_state[show_key]
                                    st.rerun()

                        with col3:
                            if st.button("✖ Dismiss", key=f"dismis_{u['user_id']}"):
                                db_update(TBL_USERS, "user_id", u["user_id"], {"password_reset_requested": "no",
                                     "reset_requested_at": None})
                                st.cache_data.clear()
                                st.rerun()
                    st.markdown("---")

    # ── All Users ──
    with tab6:
        show_cols = ["business_name","full_name","email","plan_type","plan_status","subscription_end","created_at"]
        display   = users_df[[c for c in show_cols if c in users_df.columns]]

        admin_search = st.text_input("🔍 Search users", key="admin_user_search", placeholder="Name, email or business…")
        if admin_search:
            mask = (
                display["business_name"].str.contains(admin_search, case=False, na=False) |
                display["full_name"].str.contains(admin_search, case=False, na=False) |
                display["email"].str.contains(admin_search, case=False, na=False)
            )
            display = display[mask]

        AU_PAGE = 25
        au_total = max(1, -(-len(display) // AU_PAGE))
        if "au_page" not in st.session_state:
            st.session_state.au_page = 1
        au_pg = st.session_state.au_page
        display_page = display.iloc[(au_pg - 1) * AU_PAGE: au_pg * AU_PAGE]
        st.caption(f"Showing {len(display_page)} of {len(display)} users  •  Page {au_pg} of {au_total}")
        st.dataframe(display_page, use_container_width=True)

        if au_total > 1:
            au1, au2, au3 = st.columns([1, 3, 1])
            if au1.button("◀ Prev", disabled=(au_pg <= 1), key="au_prev"):
                st.session_state.au_page = max(1, au_pg - 1)
                st.rerun()
            au2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {au_pg} of {au_total}</div>", unsafe_allow_html=True)
            if au3.button("Next ▶", disabled=(au_pg >= au_total), key="au_next"):
                st.session_state.au_page = min(au_total, au_pg + 1)
                st.rerun()

        csv = users_df[[c for c in show_cols if c in users_df.columns]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export All Users CSV", data=csv,
                           file_name="bizpulse_users.csv", mime="text/csv")

    # ── Deactivated ──
    with tab7:
        deactivated_df = users_df[users_df["plan_status"] == "expired"]
        if deactivated_df.empty:
            st.success("✅ No deactivated accounts.")
        else:
            st.info(f"{len(deactivated_df)} deactivated account(s). Choose a plan and reactivate.")
            for _, u in deactivated_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                        st.caption(
                            f"📧 {u['email']} | "
                            f"Was: {u.get('plan_type','?')} | "
                            f"Expired: {u.get('subscription_end','?')}"
                        )
                    with col2:
                        plan_choice = st.selectbox(
                            "Plan",
                            options=["monthly", "yearly"],
                            format_func=lambda x: "Monthly (30d)" if x == "monthly" else "Yearly (365d)",
                            key=f"react_plan_{u['user_id']}",
                        )
                    with col3:
                        if st.button("✅ Reactivate", key=f"reactivate_{u['user_id']}"):
                            days    = 365 if plan_choice == "yearly" else 30
                            new_end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                            ok = db_update(TBL_USERS, "user_id", u["user_id"], {
                                "plan_status":        "active",
                                "plan_type":          plan_choice,
                                "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                                "subscription_end":   new_end,
                            })
                            if ok:
                                pay_amount = (
                                    PAYMENT_DETAILS["yearly_price"]
                                    if plan_choice == "yearly"
                                    else PAYMENT_DETAILS["monthly_price"]
                                )
                                log_payment(
                                    u["user_id"], u["business_name"], u["email"],
                                    plan_choice, pay_amount, "Reactivation"
                                )
                                st.cache_data.clear()
                                st.success(f"✅ {u['business_name']} reactivated until {new_end}")
                                st.rerun()
                    st.markdown("---")


# ─────────────────────────────────────────────
#  SIDEBAR NAVIGATION
# ─────────────────────────────────────────────
