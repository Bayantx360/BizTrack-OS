# ============================================================
#  db.py — Supabase service layer (all database operations)
# ============================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
from config import (TBL_PAYMENTS, TBL_USERS, TBL_SALES,
                    TBL_PRODUCTS, TBL_EXPENSES)
from utils import gen_id


@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    """Return authenticated Supabase client. Cached for app lifetime."""
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_key"]
    return create_client(url, key)


def db_fetch(table: str, filters: dict = None) -> pd.DataFrame:
    """SELECT * FROM table WHERE filters (AND equality).
    Returns DataFrame, empty on error."""
    try:
        sb    = get_supabase()
        query = sb.table(table).select("*")
        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)
        res = query.execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error reading {table}: {e}")
        return pd.DataFrame()


def db_insert(table: str, row: dict) -> bool:
    """INSERT a single row dict into table. Returns True on success."""
    try:
        sb  = get_supabase()
        res = sb.table(table).insert(row).execute()
        st.cache_data.clear()
        return bool(res.data)
    except Exception as e:
        st.error(f"❌ Error inserting into {table}: {e}")
        return False


def db_update(table: str, id_col: str, id_val: str, updates: dict) -> bool:
    """UPDATE table SET updates WHERE id_col = id_val."""
    try:
        sb = get_supabase()
        sb.table(table).update(updates).eq(id_col, id_val).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error updating {table}: {e}")
        return False


def db_delete(table: str, id_col: str, id_val: str) -> bool:
    """DELETE FROM table WHERE id_col = id_val."""
    try:
        sb = get_supabase()
        sb.table(table).delete().eq(id_col, id_val).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error deleting from {table}: {e}")
        return False


def log_payment(user_id: str, business_name: str, email: str,
                plan_type: str, amount: float, note: str = "") -> bool:
    """Insert a payment record — ground-truth revenue ledger for the platform."""
    try:
        return db_insert(TBL_PAYMENTS, {
            "payment_id":    gen_id("PAY"),
            "user_id":       user_id,
            "business_name": business_name,
            "email":         email,
            "plan_type":     plan_type,
            "amount":        amount,
            "payment_date":  datetime.now().isoformat(),
            "note":          note,
        })
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def get_payments_df() -> pd.DataFrame:
    try:
        df = db_fetch(TBL_PAYMENTS)
        if df.empty:
            return pd.DataFrame()
        df["amount"]       = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        df["payment_date"] = pd.to_datetime(
            df["payment_date"], errors="coerce", utc=True
        ).dt.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def get_sales_df(business_id: str) -> pd.DataFrame:
    df = db_fetch(TBL_SALES, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["sale_date"]    = pd.to_datetime(
        df["sale_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    df["total_amount"] = pd.to_numeric(df["total_amount"],  errors="coerce").fillna(0)
    df["gross_profit"] = pd.to_numeric(df["gross_profit"],  errors="coerce").fillna(0)
    df["quantity"]     = pd.to_numeric(df["quantity"],      errors="coerce").fillna(0)
    df["cost_total"]   = pd.to_numeric(df["cost_total"],    errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_products_df(business_id: str) -> pd.DataFrame:
    df = db_fetch(TBL_PRODUCTS, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["selling_price"]  = pd.to_numeric(df["selling_price"],  errors="coerce").fillna(0)
    df["cost_price"]     = pd.to_numeric(df["cost_price"],     errors="coerce").fillna(0)
    df["stock_quantity"] = pd.to_numeric(df["stock_quantity"], errors="coerce").fillna(0)
    df["reorder_level"]  = pd.to_numeric(df["reorder_level"],  errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_expenses_df(business_id: str) -> pd.DataFrame:
    df = db_fetch(TBL_EXPENSES, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["amount"]       = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["expense_date"] = pd.to_datetime(
        df["expense_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    return df
