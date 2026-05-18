# ============================================================
#  pages/page_forgot.py
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


def page_forgot_password():
    inject_styles()
    st.markdown("""
<div style="max-width:440px;margin:2.5rem auto;text-align:center;margin-bottom:1rem;">
<div style="font-size:2rem;font-weight:800;color:#0f172a;">📊 BizPulse</div>
</div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div class="auth-form-wrap">', unsafe_allow_html=True)
        st.markdown("### Reset your password")
        st.markdown(
            '<div style="color:#64748b;font-size:0.875rem;margin-bottom:1.25rem;">'
            'Enter your email and we will flag your account for a password reset. '
            'You will be able to log in with a new password once it has been processed.'
            '</div>',
            unsafe_allow_html=True,
        )

        with st.form("forgot_pw_form"):
            email     = st.text_input("Email address", placeholder="you@business.com")
            submitted = st.form_submit_button("Request Password Reset →",
                                              use_container_width=True, type="primary")

        if submitted:
            if not email:
                st.error("Please enter your email address.")
            else:
                email = email.strip().lower()
                users_df = db_fetch(TBL_USERS)
                match = users_df[users_df["email"].str.lower() == email] if not users_df.empty else pd.DataFrame()

                if match.empty:
                    # Deliberately vague — do not reveal whether email exists
                    st.success(
                        "If that email is registered, a reset request has been submitted. "
                        "You will be contacted within 24 hours."
                    )
                else:
                    user_id = match.iloc[0]["user_id"]
                    ok = db_update(TBL_USERS, "user_id", user_id, {"password_reset_requested": "yes",
                         "reset_requested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    st.cache_data.clear()
                    if ok:
                        st.success(
                            "✅ Reset request submitted! Your password will be reset within 24 hours. "
                            "You will receive a new temporary password via the contact you provided."
                        )
                    else:
                        st.error("Something went wrong. Please try again.")

        st.markdown("---")
        if st.button("← Back to Sign In", use_container_width=True):
            st.session_state.auth_page = "login"
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)



# ─────────────────────────────────────────────
#  PAGE: FORCE CHANGE PASSWORD (temp password used)
# ─────────────────────────────────────────────

