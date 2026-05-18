# ============================================================
#  sidebar.py — Sidebar rendering and access control
# ============================================================

import streamlit as st
from datetime import datetime, timedelta
from shared import *


def render_sidebar():
    inject_sidebar_toggle()   # inject custom toggle tab on every logged-in render
    user     = st.session_state.get("user", {})
    is_admin = user.get("role") == "admin"
    current  = st.session_state.get("current_page", "dashboard")

    with st.sidebar:
        # ── Logo ──
        st.markdown("""
<div style="padding:1.25rem 0.5rem 1.5rem 0.5rem;">
<div style="display:flex;align-items:center;gap:0.6rem;">
<div style="
width:32px;height:32px;border-radius:8px;
background:linear-gradient(135deg,#F5A623,#C4831A);
display:flex;align-items:center;justify-content:center;
font-size:0.95rem;flex-shrink:0;
box-shadow:0 3px 10px rgba(245,166,35,0.4);
">📊</div>
<div style="
font-family:'Syne',sans-serif;
font-size:1.25rem;font-weight:800;
color:#F0F4F8;letter-spacing:-0.04em;
">BizPulse</div>
</div>
</div>
        """, unsafe_allow_html=True)

        # ── User card ──
        plan_status = user.get("plan_status","")
        plan_type   = user.get("plan_type","")
        sub_end     = user.get("subscription_end","")
        if plan_status == "active":
            end_dt    = parse_date(sub_end)
            days_left = (end_dt - datetime.now()).days if end_dt else 0
            status_color = "#F5A623" if days_left > 7 else "#FF4D6D"
            status_text  = f"{days_left}d remaining"
        else:
            status_color = "#FF4D6D"
            status_text  = "Inactive"

        st.markdown(f"""
<div style="
background:#0D1117;border:1px solid #1F2D3D;
border-radius:12px;padding:0.875rem 1rem;
margin-bottom:1.5rem;
">
<div style="font-size:0.65rem;color:#4A6080;text-transform:uppercase;
letter-spacing:0.1em;font-weight:600;margin-bottom:0.3rem;">
Active Business
</div>
<div style="font-size:0.95rem;font-weight:700;
color:#F0F4F8;font-family:'Syne',sans-serif;
letter-spacing:-0.02em;margin-bottom:0.1rem;">
{user.get('business_name','—')}
</div>
<div style="font-size:0.75rem;color:#4A6080;margin-bottom:0.5rem;">
{user.get('full_name','')}
</div>
<div style="display:flex;align-items:center;gap:0.4rem;">
<div style="width:6px;height:6px;border-radius:50%;
background:{status_color};flex-shrink:0;
box-shadow:0 0 6px {status_color};"></div>
<div style="font-size:0.7rem;color:{status_color};font-weight:600;">
{plan_type.capitalize()} · {status_text}
</div>
</div>
</div>
        """, unsafe_allow_html=True)

        # ── Navigation ──
        nav_items = [
            ("dashboard",      "🏠", "Dashboard"),
            ("record_sale",    "🛒", "Record Sale"),
            ("sales_history",  "📋", "Sales History"),
            ("products",       "📦", "Products"),
            ("expenses",       "💸", "Expenses"),
            ("insights",       "🧠", "Insights"),
        ]
        if is_admin:
            nav_items.append(("admin", "🛡️", "Admin Panel"))

        for page_key, icon, label in nav_items:
            is_active = current == page_key
            btn_style = "primary" if is_active else "secondary"
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{page_key}",
                use_container_width=True,
                type=btn_style,
            ):
                st.session_state.current_page = page_key
                st.rerun()

        # ── Bottom actions ──
        st.markdown("""
<div style="position:fixed;bottom:0;left:0;width:260px;
padding:1rem;background:#080B0F;
border-top:1px solid #1F2D3D;">
</div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
        if st.button("🔑  Change Password", use_container_width=True):
            st.session_state.current_page = "change_password"
            st.rerun()
        if st.button("🚪  Sign Out", use_container_width=True):
            for key in ["user", "logged_in", "current_page"]:
                st.session_state.pop(key, None)
            st.rerun()


# ─────────────────────────────────────────────
#  SUBSCRIPTION GUARD
# ─────────────────────────────────────────────


def check_access():
    """
    Returns True if user can access the app.
    Handles pending payment and expired subscriptions.
    """
    user = st.session_state.get("user", {})
    role = user.get("role", "")

    # Admin always has access
    if role == "admin":
        return True

    status = user.get("plan_status", "")

    if status == "pending_payment":
        page_pending_payment()
        return False

    if status == "expired":
        inject_styles()
        email = user.get("email", "")
        st.markdown(f"""
<div style="max-width:560px;margin:3rem auto;background:white;border-radius:20px;
padding:2.5rem;box-shadow:0 20px 60px rgba(0,0,0,0.08);
border:1px solid #e2e8f0;text-align:center;">
<div style="font-size:2.5rem;margin-bottom:0.5rem;">⏰</div>
<div style="font-size:1.4rem;font-weight:800;color:#0f172a;margin-bottom:0.5rem;">
Subscription Expired
</div>
<div style="color:#64748b;font-size:0.9rem;margin-bottom:2rem;">
Your access period has ended. Renew to continue using BizPulse.
</div>
<div style="background:#f8fafc;border-radius:14px;padding:1.25rem;
border:1px solid #e2e8f0;margin-bottom:1.75rem;text-align:left;">
<div style="display:flex;justify-content:space-between;margin-bottom:0.6rem;">
<span style="font-weight:600;color:#334155;">Monthly</span>
<span style="font-weight:700;color:#0f172a;">
₦{PAYMENT_DETAILS['monthly_price']:,}/month
</span>
</div>
<div style="display:flex;justify-content:space-between;">
<span style="font-weight:600;color:#334155;">Yearly</span>
<span style="font-weight:700;color:#10b981;">
₦{PAYMENT_DETAILS['yearly_price']:,}/year — save ₦3,000
</span>
</div>
</div>
<div style="font-size:0.8rem;color:#94a3b8;margin-bottom:1.5rem;">
🔒 Secure payment via Flutterwave. Reactivated within 24 hours.
</div>
</div>
        """, unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.link_button(
                f"💳 Renew Monthly — ₦{PAYMENT_DETAILS['monthly_price']:,}",
                url=PAYMENT_DETAILS["flutterwave_monthly"],
                use_container_width=True,
                type="primary",
            )
            st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)
            st.link_button(
                f"🏆 Renew Yearly — ₦{PAYMENT_DETAILS['yearly_price']:,} (best value)",
                url=PAYMENT_DETAILS["flutterwave_yearly"],
                use_container_width=True,
            )
            st.markdown("<div style='margin-top:0.75rem;'></div>", unsafe_allow_html=True)
            if st.button("Sign Out", use_container_width=True):
                for key in ["user", "logged_in", "current_page"]:
                    st.session_state.pop(key, None)
                st.rerun()
        return False

    if not is_subscription_active(user):
        # Auto-mark as expired
        db_update(TBL_USERS, "user_id", user["user_id"], {"plan_status": "expired"})
        st.session_state.user["plan_status"] = "expired"
        st.rerun()

    return True


# ─────────────────────────────────────────────
#  MAIN ROUTER
# ─────────────────────────────────────────────
