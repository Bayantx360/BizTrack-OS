# ============================================================
#  pages/page_pending.py
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


def page_pending_payment():
    inject_styles()
    user   = st.session_state.get("user", {})
    plan   = user.get("plan_type") or st.session_state.get("pending_plan", "monthly")
    email  = user.get("email")    or st.session_state.get("pending_email", "")
    amount = (PAYMENT_DETAILS["yearly_price"]
              if plan == "yearly"
              else PAYMENT_DETAILS["monthly_price"])
    fw_link = (PAYMENT_DETAILS["flutterwave_yearly"]
               if plan == "yearly"
               else PAYMENT_DETAILS["flutterwave_monthly"])
    savings_note = " — save ₦3,000!" if plan == "yearly" else ""

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(
            "<div style='text-align:center;font-size:2rem;font-weight:800;"
            #"color:#0f172a;margin-bottom:0.25rem;'>📊 BizPulse</div>",
            "color:#d4af37;margin-bottom:0.25rem;'>📊 BizPulse</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown(
            "<div style='text-align:center;font-size:2.5rem;'>🎉</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center;font-size:1.4rem;font-weight:800;"
            "color:#16a34a;margin-bottom:0.25rem;'>Account created!</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center;color:#d4af37;font-size:0.9rem;"
            "margin-bottom:1rem;'>One last step — complete your payment to activate "
            "full access.</div>",
            unsafe_allow_html=True,
        )

        # Summary box using native elements
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Plan**")
                st.markdown("**Amount**")
                st.markdown("**Email**")
            with c2:
                st.markdown(f":{plan.capitalize()}{savings_note}")
                st.markdown(f"**₦{amount:,}**")
                st.markdown(f"`{email}`")

        st.caption("🔒 Secure payment via Flutterwave. Your account will be "
                   "activated within **24 hours** after payment is confirmed.")

        st.link_button(
            f"💳 Pay ₦{amount:,} via Flutterwave →",
            url=fw_link,
            use_container_width=True,
            type="primary",
        )
        if st.button("← Back to Sign In", use_container_width=True):
            st.session_state.auth_page = "login"
            st.rerun()

        st.caption("Already paid? Your account will be activated shortly. "
                   "Contact support if you don't hear back within 24 hours.")



# ─────────────────────────────────────────────
#  PAGE: FORGOT PASSWORD
# ─────────────────────────────────────────────

