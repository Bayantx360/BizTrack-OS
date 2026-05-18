# ============================================================
#  auth.py — Authentication: login, signup, password management
# ============================================================

import streamlit as st
import bcrypt
from datetime import datetime, timedelta
from config import TBL_USERS, PAYMENT_DETAILS
from db import db_insert, get_supabase
from utils import gen_id, validate_email, parse_date


def _admin_credentials():
    return (
        st.secrets["admin"]["email"],
        st.secrets["admin"]["password"],
        st.secrets["admin"]["business_id"],
    )


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def get_user_by_email(email: str):
    """Return user dict or None."""
    try:
        sb  = get_supabase()
        res = sb.table(TBL_USERS).select("*").ilike("email", email).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Error fetching user: {e}")
        return None


def is_subscription_active(user: dict) -> bool:
    if user.get("plan_status") != "active":
        return False
    end = parse_date(user.get("subscription_end", ""))
    if end is None:
        return False
    return datetime.now() <= end


def login_user(email: str, password: str):
    """Returns (success, user_dict, message)."""
    admin_email, admin_password, admin_biz_id = _admin_credentials()

    if email.lower() == admin_email.lower() and password == admin_password:
        admin_user = {
            "user_id":       "ADMIN",
            "business_id":   admin_biz_id,
            "business_name": "BizPulse Admin",
            "full_name":     "Administrator",
            "email":         admin_email,
            "role":          "admin",
            "plan_status":   "active",
            "subscription_end": (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d"),
        }
        return True, admin_user, "Welcome, Admin!"

    user = get_user_by_email(email)
    if not user:
        return False, None, "No account found with that email."
    if not check_password(password, str(user.get("password_hash", ""))):
        return False, None, "Incorrect password."
    return True, user, "Login successful."


def signup_user(business_name, full_name, email, password, plan_type):
    """Returns (success, message)."""
    if not validate_email(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if get_user_by_email(email):
        return False, "An account with this email already exists."

    user_id     = gen_id("USR")
    business_id = gen_id("BIZ")
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if plan_type == "trial":
        status = "active"
        start  = datetime.now().strftime("%Y-%m-%d")
        end    = (datetime.now() + timedelta(
            days=PAYMENT_DETAILS["trial_days"]
        )).strftime("%Y-%m-%d")
    else:
        status = "pending_payment"
        start  = ""
        end    = ""

    success = db_insert(TBL_USERS, {
        "user_id":                  user_id,
        "business_id":              business_id,
        "business_name":            business_name,
        "full_name":                full_name,
        "email":                    email,
        "password_hash":            hash_password(password),
        "role":                     "owner",
        "plan_type":                plan_type,
        "plan_status":              status,
        "subscription_start":       start if start else None,
        "subscription_end":         end   if end   else None,
        "created_at":               now,
        "password_reset_requested": "no",
        "reset_requested_at":       None,
        "must_change_password":     "no",
    })
    if success:
        return True, "Account created successfully."
    return False, "Failed to create account. Please try again."
