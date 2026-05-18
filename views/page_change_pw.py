# ============================================================
#  pages/page_change_pw.py
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


def page_change_password(forced=True):
    inject_styles()
    user = st.session_state.get("user", {})

    _, col, _ = st.columns([1, 2, 1])
    with col:
        if forced:
            st.markdown(
                "<div style='text-align:center;font-size:2rem;'>🔐</div>"
                "<div style='text-align:center;font-size:1.3rem;font-weight:800;"
                "color:#0f172a;margin-bottom:0.25rem;'>Set your new password</div>"
                "<div style='text-align:center;color:#64748b;font-size:0.875rem;"
                "margin-bottom:1.5rem;'>Your account was accessed with a temporary password. "
                "You must set a permanent password before continuing.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("### 🔑 Change Password")

        with st.form("change_pw_form"):
            if not forced:
                current_pw = st.text_input("Current password", type="password")
            new_pw     = st.text_input("New password (min 6 chars)", type="password")
            confirm_pw = st.text_input("Confirm new password", type="password")
            submitted  = st.form_submit_button(
                "Set New Password →", use_container_width=True, type="primary"
            )

        if submitted:
            # Verify current password if not forced
            if not forced:
                if not check_password(current_pw, str(user.get("password_hash", ""))):
                    st.error("Current password is incorrect.")
                    st.stop()
            if not new_pw or len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            else:
                hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
                ok = db_update(TBL_USERS, "user_id", user["user_id"], {
                        "password_hash":        hashed,
                        "must_change_password": "no",
                    })
                st.cache_data.clear()
                if ok:
                    # Update session so the flag is cleared
                    st.session_state.user["password_hash"]        = hashed
                    st.session_state.user["must_change_password"] = "no"
                    st.success("✅ Password updated successfully!")
                    st.session_state.current_page = "dashboard"
                    st.rerun()
                else:
                    st.error("Failed to update password. Please try again.")

        if not forced:
            if st.button("← Back", use_container_width=True):
                st.session_state.current_page = "dashboard"
                st.rerun()


# ─────────────────────────────────────────────
#  PAGE: DASHBOARD
# ─────────────────────────────────────────────

