# ============================================================
#  pages/page_signup.py
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


def page_signup():
    inject_styles()

    # ── Hero ──
    st.markdown("""
<div style="text-align:center;padding:2.5rem 1rem 0.5rem 1rem;">
<div style="display:inline-flex;align-items:center;gap:0.7rem;margin-bottom:1.25rem;">
<div style="
width:48px;height:48px;border-radius:14px;
background:linear-gradient(135deg,#F5A623,#C4831A);
display:flex;align-items:center;justify-content:center;
font-size:1.4rem;
box-shadow:0 6px 24px rgba(245,166,35,0.4);
">📊</div>
<div style="
font-family:'Syne',sans-serif;
font-size:2rem;font-weight:800;
color:#F0F4F8;letter-spacing:-0.05em;
">BizPulse</div>
</div>
<div style="
font-family:'Syne',sans-serif;
font-size:1.5rem;font-weight:700;
color:#F0F4F8;letter-spacing:-0.03em;
margin-bottom:0.6rem;line-height:1.2;
">
Know your numbers.<br>
<span style="color:#F5A623;">Grow your business.</span>
</div>
<div style="
font-size:0.9rem;color:#4A6080;
max-width:460px;margin:0 auto;line-height:1.6;
">
Sales tracking · Inventory management · Expense control ·
Profit analytics — built for Nigerian SMEs.
</div>
<div style="
display:inline-flex;align-items:center;gap:0.5rem;
margin-top:1.25rem;
background:#0D1117;border:1px solid #1F2D3D;
border-radius:99px;padding:0.4rem 1rem;
font-size:0.78rem;color:#8BA0B8;
">
<span style="color:#F5A623;">●</span>
14-day free trial · No card required · Cancel anytime
</div>
</div>
    """, unsafe_allow_html=True)

    # ── Pricing Cards ──
    st.markdown("""
<div class="pricing-grid">
<div class="pricing-card">
<div class="pricing-plan-name">Free Trial</div>
<div class="pricing-price">₦0<span>/14 days</span></div>
<div class="pricing-desc">No card required. Full access.</div>
<ul class="pricing-features">
<li>Sales recording</li>
<li>Inventory management</li>
<li>Expense tracking</li>
<li>Dashboard analytics</li>
<li>Up to 50 products</li>
</ul>
</div>

<div class="pricing-card featured">
<div class="pricing-badge">Most Popular</div>
<div class="pricing-plan-name">Monthly</div>
<div class="pricing-price">₦1,500<span>/mo</span></div>
<div class="pricing-desc">Billed monthly. Cancel anytime.</div>
<ul class="pricing-features">
<li>Everything in Trial</li>
<li>Unlimited products</li>
<li>Business insights</li>
<li>Sales trend reports</li>
<li>Low stock alerts</li>
</ul>
</div>

<div class="pricing-card">
<div class="pricing-badge" style="background:#00C896;color:#080B0F;">Save ₦3,000</div>
<div class="pricing-plan-name">Yearly</div>
<div class="pricing-price">₦15,000<span>/yr</span></div>
<div class="pricing-desc">₦1,250/month · 2 months free</div>
<ul class="pricing-features">
<li>Everything in Monthly</li>
<li>Best value plan</li>
<li>Priority activation</li>
<li>Full year coverage</li>
<li>2 months free</li>
</ul>
</div>

</div>
    """, unsafe_allow_html=True)

    # ── Signup Form ──
    st.markdown("---")
    st.markdown("### Create your account")

    # Plan selector outside the form so it shows clearly
    plan = st.radio(
        "Choose your plan",
        options=["trial", "monthly", "yearly"],
        format_func=lambda x: {
            "trial":   f"🎁 Free Trial — 14 days free, no payment",
            "monthly": f"📅 Monthly — ₦1,500/month",
            "yearly":  f"🏆 Yearly — ₦15,000/year  (save ₦3,000!)",
        }[x],
        horizontal=True,
        key="signup_plan_select",
    )

    with st.form("signup_form"):
        col1, col2 = st.columns(2)
        with col1:
            business_name = st.text_input("Business name", placeholder="Mama Put Express")
            email         = st.text_input("Email address", placeholder="you@business.com")
            password      = st.text_input("Password (min 6 chars)", type="password")
        with col2:
            full_name  = st.text_input("Your full name", placeholder="Adaeze Okafor")
            confirm_pw = st.text_input("Confirm password", type="password")

        btn_label = {
            "trial":   "Start Free Trial →",
            "monthly": "Create Account & Pay Monthly →",
            "yearly":  "Create Account & Pay Yearly →",
        }.get(plan, "Create Account →")

        submitted = st.form_submit_button(btn_label, use_container_width=True, type="primary")

    if submitted:
        _plan = st.session_state.get("signup_plan_select", plan)
        if not all([business_name, full_name, email, password, confirm_pw]):
            st.error("Please fill in all fields.")
        elif password != confirm_pw:
            st.error("Passwords do not match.")
        else:
            with st.spinner("Creating your account…"):
                ok, msg = signup_user(business_name.strip(), full_name.strip(),
                                      email.strip(), password, _plan)
            if ok:
                if _plan == "trial":
                    st.success("🎉 Your 14-day free trial is active! Sign in to get started.")
                    st.session_state.auth_page = "login"
                    st.rerun()
                else:
                    st.session_state.pending_email = email.strip()
                    st.session_state.pending_plan  = _plan
                    st.session_state.auth_page     = "pending"
                    st.rerun()
            else:
                st.error(msg)

    st.markdown("---")
    if st.button("Already have an account? Sign in →", use_container_width=True):
        st.session_state.auth_page = "login"
        st.rerun()


# ─────────────────────────────────────────────
#  PAGE: PENDING PAYMENT
# ─────────────────────────────────────────────

