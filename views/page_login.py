# ============================================================
#  pages/page_login.py
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


def page_login():
    inject_styles()

    # ── Premium landing hero above the fold ──
    st.markdown("""
<div class="lp-hero">
<div class="lp-logo-wrap">
<div class="lp-logo-icon">📊</div>
<div class="lp-logo-text">BizPulse</div>
</div>
<div class="lp-badge">
<span>&#9679;</span> Built for Nigerian SMEs &middot; Powered by real-time data
</div>
<div class="lp-headline">
Run your business<br>like you <span>know your numbers.</span>
</div>
<div class="lp-sub">
Sales tracking, inventory control, expense management and profit analytics &#8212;
all in one dashboard designed for the way Nigerian businesses actually work.
</div>

<div class="lp-value-grid">
<div class="lp-value-card">
<div class="lp-value-icon">🛒</div>
<div class="lp-value-title">Sales Tracking</div>
<div class="lp-value-desc">Record every sale instantly. See today, weekly &amp; monthly revenue at a glance.</div>
</div>
<div class="lp-value-card">
<div class="lp-value-icon">📦</div>
<div class="lp-value-title">Inventory Control</div>
<div class="lp-value-desc">Track stock levels, get low-stock alerts and never run out of top sellers.</div>
</div>
<div class="lp-value-card">
<div class="lp-value-icon">💸</div>
<div class="lp-value-title">Expense Manager</div>
<div class="lp-value-desc">Log every expense, see where your money goes and protect your profit margins.</div>
</div>
<div class="lp-value-card">
<div class="lp-value-icon">🧠</div>
<div class="lp-value-title">Profit Insights</div>
<div class="lp-value-desc">Gross profit, net profit, best-selling products and trend reports &#8212; all automatic.</div>
</div>
</div>
</div>

<div class="lp-divider"><span>Sign in to your account</span></div>
    """, unsafe_allow_html=True)

    # ── Login form — centred, clean ──
    _, mid, _ = st.columns([1, 2, 1])

    with mid:
        with st.form("login_form"):
            email    = st.text_input("Email address", placeholder="you@business.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button(
                "Sign In →", use_container_width=True, type="primary"
            )

        if submitted:
            if not email or not password:
                st.error("Please fill in all fields.")
            else:
                with st.spinner("Authenticating…"):
                    ok, user, msg = login_user(email.strip(), password)
                if ok:
                    st.session_state.user         = user
                    st.session_state.logged_in    = True
                    if str(user.get("must_change_password", "")).lower() == "yes":
                        st.session_state.current_page = "change_password"
                    else:
                        st.session_state.current_page = "dashboard"
                    st.rerun()
                else:
                    st.error(msg)

        # ── Navigation buttons — outside form ──
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Forgot password?", key="goto_forgot",
                         use_container_width=True):
                st.session_state.auth_page = "forgot"
                st.rerun()
        with col_b:
            if st.button("Create account →", key="goto_signup",
                         use_container_width=True):
                st.session_state.auth_page = "signup"
                st.rerun()

    # ── Trust strip ──
    st.markdown("""
<div class="lp-trust-strip">
<div class="lp-trust-item"><span>✓</span> 256-bit encrypted</div>
<div class="lp-trust-item"><span>✓</span> Your data is never shared</div>
<div class="lp-trust-item"><span>✓</span> 14-day free trial</div>
<div class="lp-trust-item"><span>✓</span> No credit card required</div>
<div class="lp-trust-item"><span>✓</span> Cancel anytime</div>
</div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  PAGE: SIGNUP
# ─────────────────────────────────────────────

