"""
shared/db.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Unified Supabase Service Layer
══════════════════════════════════════════════════════════════════════

Single source of truth for:
  • Supabase client (one cached connection for the whole suite)
  • Generic CRUD helpers  (db_fetch, db_insert, db_update, db_delete)
  • Typed data loaders    (get_sales_df, get_products_df, get_expenses_df)
  • Cross-app analytics   (compute_kpis, compute_insights)
  • Payment helpers       (log_payment, get_payments_df)

All three page modules import from here:
    from shared.db import (
        get_supabase,
        db_fetch, db_insert, db_update, db_delete,
        get_sales_df, get_products_df, get_expenses_df,
        compute_kpis, compute_insights,
        log_payment, get_payments_df,
        get_debts_df, get_debt_payments_df, record_debt_payment,
        get_suppliers_df,
        TBL_USERS, TBL_PRODUCTS, TBL_SALES, TBL_EXPENSES,
        TBL_PAYMENTS, TBL_RESTOCK, TBL_SALE_ITEMS,
        TBL_DEBTS, TBL_DEBT_PAYMENTS, TBL_SUPPLIERS,
        PAYMENT_DETAILS,
    )
"""

from __future__ import annotations

import uuid
import re
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ── Table name constants ───────────────────────────────────────────────────────
TBL_USERS         = "users"
TBL_PRODUCTS      = "products"
TBL_SALES         = "sales"
TBL_EXPENSES      = "expenses"
TBL_PAYMENTS      = "payments"
TBL_RESTOCK       = "restock_log"
TBL_SALE_ITEMS    = "sale_items"
TBL_DEBTS         = "debts"
TBL_DEBT_PAYMENTS = "debt_payments"
TBL_SUPPLIERS     = "suppliers"
TBL_ACTIVITY      = "user_activity"

# ── Supported countries config ────────────────────────────────────────────────
# Each entry: country_name → { code, currency_code, currency_symbol, dial_code }
SUPPORTED_COUNTRIES: dict[str, dict] = {
    # ── Tier 1: Africa ────────────────────────────────────────────────────────
    "Nigeria":          {"code": "NG", "currency_code": "NGN", "currency_symbol": "₦",    "dial_code": "+234"},
    "Ghana":            {"code": "GH", "currency_code": "GHS", "currency_symbol": "GH₵",  "dial_code": "+233"},
    "Kenya":            {"code": "KE", "currency_code": "KES", "currency_symbol": "KSh",  "dial_code": "+254"},
    "South Africa":     {"code": "ZA", "currency_code": "ZAR", "currency_symbol": "R",    "dial_code": "+27"},
    "Tanzania":         {"code": "TZ", "currency_code": "TZS", "currency_symbol": "TSh",  "dial_code": "+255"},
    "Uganda":           {"code": "UG", "currency_code": "UGX", "currency_symbol": "USh",  "dial_code": "+256"},
    "Rwanda":           {"code": "RW", "currency_code": "RWF", "currency_symbol": "FRw",  "dial_code": "+250"},
    "Zambia":           {"code": "ZM", "currency_code": "ZMW", "currency_symbol": "ZK",   "dial_code": "+260"},
    "Cameroon":         {"code": "CM", "currency_code": "XAF", "currency_symbol": "FCFA", "dial_code": "+237"},
    "Senegal":          {"code": "SN", "currency_code": "XOF", "currency_symbol": "CFA",  "dial_code": "+221"},
    "Ethiopia":         {"code": "ET", "currency_code": "ETB", "currency_symbol": "Br",   "dial_code": "+251"},
    "Egypt":            {"code": "EG", "currency_code": "EGP", "currency_symbol": "E£",   "dial_code": "+20"},
    # ── Tier 2: English-speaking west ─────────────────────────────────────────
    "United Kingdom":   {"code": "GB", "currency_code": "GBP", "currency_symbol": "£",    "dial_code": "+44"},
    "United States":    {"code": "US", "currency_code": "USD", "currency_symbol": "$",    "dial_code": "+1"},
    "Canada":           {"code": "CA", "currency_code": "CAD", "currency_symbol": "CA$",  "dial_code": "+1"},
    "Australia":        {"code": "AU", "currency_code": "AUD", "currency_symbol": "A$",   "dial_code": "+61"},
    "Ireland":          {"code": "IE", "currency_code": "EUR", "currency_symbol": "€",    "dial_code": "+353"},
    # ── Tier 3: Opportunistic ─────────────────────────────────────────────────
    "UAE":              {"code": "AE", "currency_code": "AED", "currency_symbol": "AED",  "dial_code": "+971"},
    "India":            {"code": "IN", "currency_code": "INR", "currency_symbol": "₹",    "dial_code": "+91"},
    "Germany":          {"code": "DE", "currency_code": "EUR", "currency_symbol": "€",    "dial_code": "+49"},
    "France":           {"code": "FR", "currency_code": "EUR", "currency_symbol": "€",    "dial_code": "+33"},
    "Netherlands":      {"code": "NL", "currency_code": "EUR", "currency_symbol": "€",    "dial_code": "+31"},
    "Saudi Arabia":     {"code": "SA", "currency_code": "SAR", "currency_symbol": "SAR",  "dial_code": "+966"},
    "Pakistan":         {"code": "PK", "currency_code": "PKR", "currency_symbol": "₨",    "dial_code": "+92"},
    "Brazil":           {"code": "BR", "currency_code": "BRL", "currency_symbol": "R$",   "dial_code": "+55"},
}

# ── Plan / payment config ──────────────────────────────────────────────────────
PAYMENT_DETAILS = {
    "trial_days": 14,
    "NG": {
        "monthly_price":       1500,
        "yearly_price":        15000,
        "currency_label":      "₦",
        "flutterwave_monthly": "https://flutterwave.com/pay/e2jsc3ckyfya",
        "flutterwave_yearly":  "https://flutterwave.com/pay/ztzprecyyhg2",
    },
    "GLOBAL": {
        "monthly_price":       3,
        "yearly_price":        25,
        "currency_label":      "$",
        "flutterwave_monthly": "https://flutterwave.com/pay/trp1jdz0emrg",
        "flutterwave_yearly":  "https://flutterwave.com/pay/l8gbytdsx359",
    },
}


def get_payment_plan(country_code: str) -> dict:
    """
    Return the correct pricing/payment dict for a given country code.
    Nigeria (NG) gets the legacy Naira plan; everyone else gets the
    global USD plan. Safe fallback to GLOBAL if country_code is missing
    or unrecognized — never raises.
    """
    if not country_code:
        return PAYMENT_DETAILS["GLOBAL"]
    return PAYMENT_DETAILS.get(country_code.upper(), PAYMENT_DETAILS["GLOBAL"])


# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE CLIENT
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    """
    Return the authenticated Supabase client.
    Cached at the resource level — one connection for the entire server process,
    shared across all three app modules.
    """
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_key"]
    return create_client(url, key)


# ══════════════════════════════════════════════════════════════════════════════
# GENERIC CRUD HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_FETCH_PAGE_SIZE = 1000  # Supabase default cap per request

def db_fetch(table: str, filters: dict = None) -> pd.DataFrame:
    """
    SELECT * FROM table WHERE filters (all AND equality).
    filters = {"column": "value"}
    Paginates automatically so results beyond the 1,000-row Supabase
    default are never silently dropped.
    Returns DataFrame, empty on error.
    """
    try:
        sb    = get_supabase()
        rows  = []
        start = 0
        while True:
            end   = start + _FETCH_PAGE_SIZE - 1
            query = sb.table(table).select("*")
            if filters:
                for col, val in filters.items():
                    query = query.eq(col, val)
            res   = query.range(start, end).execute()
            batch = res.data or []
            rows.extend(batch)
            if len(batch) < _FETCH_PAGE_SIZE:
                # Received fewer rows than page size — we're done
                break
            start += _FETCH_PAGE_SIZE
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error reading {table}: {e}")
        return pd.DataFrame()


def db_insert(table: str, row: dict, clear_cache: bool = True) -> bool:
    """
    INSERT a single row dict into table. Returns True on success.
    clear_cache=False lets a caller doing several writes in a row (e.g. a
    cart checkout) defer invalidation and clear once at the end instead of
    once per write.
    """
    try:
        sb  = get_supabase()
        res = sb.table(table).insert(row).execute()
        if clear_cache:
            clear_table_cache(table)
        return bool(res.data)
    except Exception as e:
        st.error(f"❌ Error inserting into {table}: {e}")
        return False


def db_insert_many(table: str, rows: list[dict], clear_cache: bool = True) -> bool:
    """
    INSERT multiple row dicts into table in a single request instead of
    looping db_insert() per row. Use for cart checkout (sale_items), bulk
    imports, or any place writing several rows of the same table at once.
    Returns True only if every row was written.
    """
    if not rows:
        return True
    try:
        sb  = get_supabase()
        res = sb.table(table).insert(rows).execute()
        if clear_cache:
            clear_table_cache(table)
        return bool(res.data) and len(res.data) == len(rows)
    except Exception as e:
        st.error(f"❌ Error bulk-inserting into {table}: {e}")
        return False


def log_activity(business_id: str, event_type: str, subscription_status: str = "active") -> None:
    """
    Append a single activity event to user_activity.
    Fire-and-forget — errors are silently swallowed so they never
    interrupt the main user flow.

    event_type values used across the suite:
        "login"            — user authenticated successfully
        "sale_recorded"    — a sale was committed to the DB
        "signup"           — new account created

    subscription_status: 'trial' | 'active' | 'expired'
    """
    try:
        sb = get_supabase()
        sb.table(TBL_ACTIVITY).insert({
            "business_id":         business_id,
            "event_type":          event_type,
            "subscription_status": subscription_status,
            "created_at":          datetime.now().isoformat(),
        }).execute()
    except Exception:
        pass  # never surface activity-log errors to the user


def db_update(table: str, id_col: str, id_val: str, updates: dict, clear_cache: bool = True) -> bool:
    """
    UPDATE table SET updates WHERE id_col = id_val. Returns True only if a row was actually changed.
    clear_cache=False lets a caller doing several updates in a row (e.g. deducting
    stock for every cart item) defer invalidation and clear once at the end.
    """
    try:
        sb  = get_supabase()
        res = sb.table(table).update(updates).eq(id_col, id_val).execute()
        if clear_cache:
            clear_table_cache(table)
        # Supabase returns the updated rows in res.data — empty list means nothing matched / RLS blocked it
        if not res.data:
            st.error(f"❌ Update on {table} matched no rows (check RLS policies and id value: {id_val})")
            return False
        return True
    except Exception as e:
        st.error(f"❌ Error updating {table}: {e}")
        return False


def db_delete(table: str, id_col: str, id_val: str, clear_cache: bool = True) -> bool:
    """DELETE FROM table WHERE id_col = id_val."""
    try:
        sb = get_supabase()
        sb.table(table).delete().eq(id_col, id_val).execute()
        if clear_cache:
            clear_table_cache(table)
        return True
    except Exception as e:
        st.error(f"❌ Error deleting from {table}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def log_payment(user_id: str, business_name: str, email: str,
                plan_type: str, amount: float, note: str = "",
                currency_code: str = "NGN") -> bool:
    """Insert a payment record into the platform revenue ledger."""
    try:
        return db_insert(TBL_PAYMENTS, {
            "payment_id":    gen_id("PAY"),
            "user_id":       user_id,
            "business_name": business_name,
            "email":         email,
            "plan_type":     plan_type,
            "amount":        amount,
            "currency_code": currency_code,
            "payment_date":  datetime.now().isoformat(),
            "note":          note,
        })
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def get_payments_df() -> pd.DataFrame:
    """Read payments table with typed columns. Returns empty DataFrame on error."""
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


# ══════════════════════════════════════════════════════════════════════════════
# TYPED DATA LOADERS
# Cached per business_id with a short TTL so all three apps stay in sync.
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=120, show_spinner=False)
def get_sales_df(business_id: str) -> pd.DataFrame:
    """Return typed sales DataFrame for this business."""
    df = db_fetch(TBL_SALES, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["sale_date"]    = pd.to_datetime(
        df["sale_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0)
    df["gross_profit"] = pd.to_numeric(df["gross_profit"], errors="coerce").fillna(0)
    df["quantity"]     = pd.to_numeric(df["quantity"],     errors="coerce").fillna(0)
    df["cost_total"]   = pd.to_numeric(df["cost_total"],   errors="coerce").fillna(0)
    # amount_paid must be cast so compute_kpis can sum it for the cash breakdown
    if "amount_paid" in df.columns:
        df["amount_paid"] = pd.to_numeric(df["amount_paid"], errors="coerce").fillna(0)
    else:
        df["amount_paid"] = df["total_amount"]  # fallback: treat all as collected
    return df


@st.cache_data(ttl=15, show_spinner=False)
def get_products_df_live(business_id: str) -> pd.DataFrame:
    """
    Return typed products DataFrame — 15s cache.
    Short TTL keeps stock counts accurate for sales and low-stock alerts
    while reducing repeated Supabase hits across concurrent users.
    Cache is cleared immediately on any db_insert/db_update/db_delete.
    """
    return _type_products_df(db_fetch(TBL_PRODUCTS, {"business_id": business_id}))


@st.cache_data(ttl=120, show_spinner=False)
def get_products_df(business_id: str) -> pd.DataFrame:
    """Return typed products DataFrame — cached 30s. Use for reports/insights."""
    df = db_fetch(TBL_PRODUCTS, {"business_id": business_id})
    return _type_products_df(df)


def _type_products_df(df: pd.DataFrame) -> pd.DataFrame:
    """Apply correct types to a raw products DataFrame."""
    if df.empty:
        return pd.DataFrame()
    df["selling_price"]     = pd.to_numeric(df["selling_price"],     errors="coerce").fillna(0)
    df["cost_price"]        = pd.to_numeric(df["cost_price"],        errors="coerce").fillna(0)
    df["stock_quantity"]    = pd.to_numeric(df["stock_quantity"],    errors="coerce").fillna(0)
    df["reorder_level"]     = pd.to_numeric(df["reorder_level"],     errors="coerce").fillna(0)
    df["units_per_pack"]    = pd.to_numeric(df.get("units_per_pack", 1),    errors="coerce").fillna(1).astype(int)
    df["selling_price_sub"] = pd.to_numeric(df.get("selling_price_sub", 0), errors="coerce").fillna(0)
    if "base_unit" not in df.columns: df["base_unit"] = "unit"
    if "sub_unit"  not in df.columns: df["sub_unit"]  = "unit"
    df["base_unit"] = df["base_unit"].fillna("unit")
    df["sub_unit"]  = df["sub_unit"].fillna("unit")
    # ── Expiry / manufacturing dates (optional — NaT for products with no dates set) ──
    df["mfg_date"]    = pd.to_datetime(df.get("mfg_date"),    errors="coerce", utc=False)
    df["expiry_date"] = pd.to_datetime(df.get("expiry_date"), errors="coerce", utc=False)
    return df


@st.cache_data(ttl=120, show_spinner=False)
def get_expenses_df(business_id: str) -> pd.DataFrame:
    """Return typed expenses DataFrame for this business."""
    df = db_fetch(TBL_EXPENSES, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["amount"]       = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["expense_date"] = pd.to_datetime(
        df["expense_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    return df


@st.cache_data(ttl=60, show_spinner=False)
def get_restock_df(business_id: str) -> pd.DataFrame:
    """Return restock log for this business — cached 60s."""
    df = db_fetch(TBL_RESTOCK, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["restock_date"] = pd.to_datetime(
        df["restock_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    return df


@st.cache_data(ttl=60, show_spinner=False)
def get_suppliers_df(business_id: str) -> pd.DataFrame:
    """Return suppliers directory for this business — cached 60s."""
    df = db_fetch(TBL_SUPPLIERS, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(
            df["created_at"], errors="coerce", utc=True
        ).dt.tz_localize(None)
    return df


@st.cache_data(ttl=60, show_spinner=False)
def get_sale_items_df(business_id: str) -> pd.DataFrame:
    """Return sale items for this business — cached 60s."""
    df = db_fetch(TBL_SALE_ITEMS, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_debts_df(business_id: str) -> pd.DataFrame:
    """Return all debt records for this business — cached 30s."""
    df = db_fetch(TBL_DEBTS, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0)
    df["amount_paid"]  = pd.to_numeric(df["amount_paid"],  errors="coerce").fillna(0)
    df["balance"]      = pd.to_numeric(df["balance"],      errors="coerce").fillna(0)
    df["sale_date"]    = pd.to_datetime(df["sale_date"],   errors="coerce", utc=True).dt.tz_localize(None)
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_debt_payments_df(business_id: str) -> pd.DataFrame:
    """Return all debt instalment records for this business — cached 30s."""
    df = db_fetch(TBL_DEBT_PAYMENTS, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["amount"]       = pd.to_numeric(df["amount"],        errors="coerce").fillna(0)
    df["payment_date"] = pd.to_datetime(df["payment_date"], errors="coerce", utc=True).dt.tz_localize(None)
    return df


# ── Scoped cache invalidation ──────────────────────────────────────────────────
# Maps each table to the @st.cache_data getters that read from it. A write to
# one table should only invalidate the getters backed by that table — not
# every cached dataframe for every business on the server. Defined here
# (after the getters above) so the function objects already exist; Python
# only looks this dict up when clear_table_cache() is actually called, by
# which point the whole module has finished loading.
_TABLE_CACHE_MAP: dict[str, tuple] = {
    TBL_PAYMENTS:      (get_payments_df,),
    TBL_SALES:         (get_sales_df,),
    TBL_PRODUCTS:      (get_products_df_live, get_products_df),
    TBL_EXPENSES:      (get_expenses_df,),
    TBL_RESTOCK:       (get_restock_df,),
    TBL_SUPPLIERS:     (get_suppliers_df,),
    TBL_SALE_ITEMS:    (get_sale_items_df,),
    TBL_DEBTS:         (get_debts_df,),
    TBL_DEBT_PAYMENTS: (get_debt_payments_df,),
}


def clear_table_cache(table: str) -> None:
    """
    Clear only the cached getter(s) backed by this table, instead of wiping
    every cached dataframe for every business (the old st.cache_data.clear()
    behavior). Tables with no cached getter (e.g. "users", user_activity) are
    a safe no-op.
    """
    for fn in _TABLE_CACHE_MAP.get(table, ()):
        try:
            fn.clear()
        except Exception:
            pass


def get_products_by_ids(business_id: str, product_ids: list[str]) -> pd.DataFrame:
    """
    Fetch only the given product_ids for this business — used for the
    pre-commit stock-conflict check at checkout, where we only ever need
    the handful of products actually in the cart, not the full catalogue.
    Not cached: this is intentionally always a live read for a small,
    bounded number of rows.
    """
    if not product_ids:
        return pd.DataFrame()
    try:
        sb  = get_supabase()
        res = (
            sb.table(TBL_PRODUCTS)
            .select("*")
            .eq("business_id", business_id)
            .in_("product_id", list(product_ids))
            .execute()
        )
        return _type_products_df(pd.DataFrame(res.data or []))
    except Exception as e:
        st.error(f"❌ Error reading products: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=15, show_spinner=False)
def search_products(business_id: str, query: str, limit: int = 30,
                     in_stock_only: bool = False) -> pd.DataFrame:
    """
    Search products by name, done in Postgres instead of pandas.
    Requires the trigram index from supabase/migrations/001_product_search_index.sql
    to stay fast as the catalogue grows — without it this still works
    correctly, just without the index speedup.

    Always returns at most `limit` rows, so search cost stays flat whether
    the business has 50 SKUs or 5,000 — unlike the old approach of fetching
    the whole table and filtering in pandas. Cached for 15s (same window as
    get_products_df_live) so repeated calls with the same arguments — e.g.
    Streamlit re-running every tab's code on every rerun — hit cache instead
    of firing a fresh network round-trip each time. 15s staleness is fine
    for search/selection; checkout still re-validates stock live via
    get_products_by_ids() at commit time, so this cache never affects
    what actually gets sold.

    query="" (or shorter than 2 characters) returns a small default page
    instead of the whole catalogue, so the caller never has to render a
    multi-thousand-row selectbox.
    """
    try:
        sb = get_supabase()
        q = (
            sb.table(TBL_PRODUCTS)
            .select("*")
            .eq("business_id", business_id)
        )
        query = (query or "").strip()
        if len(query) >= 2:
            q = q.ilike("product_name", f"%{query}%")
        if in_stock_only:
            q = q.gt("stock_quantity", 0)
        q = q.order("product_name").limit(limit)
        res = q.execute()
        return _type_products_df(pd.DataFrame(res.data or []))
    except Exception as e:
        st.error(f"❌ Error searching products: {e}")
        return pd.DataFrame()


# search_products is defined after _TABLE_CACHE_MAP above, so it's registered
# here — a write to products should invalidate this cache too, not just
# get_products_df_live/get_products_df, so restocks/sales show up in search
# immediately rather than waiting out the 15s TTL.
_TABLE_CACHE_MAP[TBL_PRODUCTS] = _TABLE_CACHE_MAP[TBL_PRODUCTS] + (search_products,)


def get_recent_restocks_for_product(business_id: str, product_id: str, limit: int = 5) -> pd.DataFrame:
    """
    Fetch only the last `limit` restock entries for ONE product — used by the
    "Recent Deliveries" panel on the Restock tab. Unlike get_restock_df(),
    which downloads the business's ENTIRE restock history (something that
    only grows over time, unlike catalogue size, which is naturally bounded),
    this scopes the query to exactly the rows being displayed. Not cached:
    restock history for one product is a small, cheap query even live.
    """
    try:
        sb  = get_supabase()
        res = (
            sb.table(TBL_RESTOCK)
            .select("*")
            .eq("business_id", business_id)
            .eq("product_id", product_id)
            .order("restock_date", desc=True)
            .limit(limit)
            .execute()
        )
        df = pd.DataFrame(res.data or [])
        if not df.empty:
            df["restock_date"] = pd.to_datetime(df["restock_date"], errors="coerce")
        return df
    except Exception as e:
        st.error(f"❌ Error reading restock history: {e}")
        return pd.DataFrame()


def record_debt_payment(debt_id: str, business_id: str,
                        amount: float, note: str = "") -> bool:
    """
    Log a debt instalment and update the parent debt record atomically.
    Updates amount_paid, balance, and status on the debts row.
    Returns True only if both writes succeed.
    """
    try:
        sb  = get_supabase()
        res = sb.table(TBL_DEBTS).select("*").eq("debt_id", debt_id).execute()
        if not res.data:
            st.error("Debt record not found.")
            return False
        debt       = res.data[0]
        new_paid   = round(float(debt["amount_paid"]) + amount, 2)
        new_bal    = round(max(float(debt["total_amount"]) - new_paid, 0), 2)
        new_status = "settled" if new_bal <= 0 else "partial"

        pay_ok = db_insert(TBL_DEBT_PAYMENTS, {
            "dpay_id":      gen_id("DPY"),
            "debt_id":      debt_id,
            "business_id":  business_id,
            "amount":       amount,
            "payment_date": datetime.now().isoformat(),
            "note":         note,
        })
        if not pay_ok:
            return False

        return db_update(TBL_DEBTS, "debt_id", debt_id, {
            "amount_paid": new_paid,
            "balance":     new_bal,
            "status":      new_status,
        })
    except Exception as e:
        st.error(f"Error recording debt payment: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-APP ANALYTICS
# Used by both the Sales app (dashboard KPIs) and the Business Health app.
# ══════════════════════════════════════════════════════════════════════════════

def compute_kpis(sales_df: pd.DataFrame, expenses_df: pd.DataFrame) -> dict:
    """
    Return a dict of key performance metrics spanning sales + expenses.
    Called by:  pages/sales.py  (dashboard KPI cards)
                pages/health.py (KPI summary + net profit)
    """
    now   = datetime.now()
    today = now.date()

    kpis = {
        "today_revenue":          0, "week_revenue":    0, "month_revenue":  0,
        "today_profit":           0, "week_profit":     0, "month_profit":   0,
        "today_txn":              0, "week_txn":        0, "month_txn":      0,
        "week_growth":            0, "month_expenses":  0, "net_profit":     0,
        "year_revenue":           0, "year_profit":     0, "year_txn":       0,
        "alltime_revenue":        0, "alltime_profit":  0, "alltime_txn":    0,
        "avg_daily_revenue":      0,
        # Cash transparency — today only
        "today_collected":        0,  # actual cash received today (amount_paid)
        "today_credit_extended":  0,  # credit still outside today (total - paid)
    }

    if sales_df.empty:
        return kpis

    df = sales_df.dropna(subset=["sale_date"])

    today_df   = df[df["sale_date"].dt.date == today]
    week_df    = df[df["sale_date"] >= (now - timedelta(days=7))]
    month_start = datetime(now.year, now.month, 1)
    month_df   = df[(df["sale_date"] >= month_start) & (df["sale_date"] <= now)]
    prev_week  = df[
        (df["sale_date"] >= (now - timedelta(days=14))) &
        (df["sale_date"] <  (now - timedelta(days=7)))
    ]

    kpis["today_revenue"]  = today_df["total_amount"].sum()
    kpis["week_revenue"]   = week_df["total_amount"].sum()
    kpis["month_revenue"]  = month_df["total_amount"].sum()
    kpis["today_profit"]   = today_df["gross_profit"].sum()
    kpis["week_profit"]    = week_df["gross_profit"].sum()
    kpis["month_profit"]   = month_df["gross_profit"].sum()
    kpis["today_txn"]      = len(today_df)
    kpis["week_txn"]       = len(week_df)
    kpis["month_txn"]      = len(month_df)

    # Cash transparency breakdown for today
    if "amount_paid" in today_df.columns:
        kpis["today_collected"]       = today_df["amount_paid"].sum()
        kpis["today_credit_extended"] = today_df["total_amount"].sum() - kpis["today_collected"]
    else:
        kpis["today_collected"]       = kpis["today_revenue"]
        kpis["today_credit_extended"] = 0

    prev_rev = prev_week["total_amount"].sum()
    curr_rev = kpis["week_revenue"]
    if prev_rev > 0:
        kpis["week_growth"] = ((curr_rev - prev_rev) / prev_rev) * 100

    if not expenses_df.empty:
        m_exp = expenses_df[
            (expenses_df["expense_date"] >= month_start) &
            (expenses_df["expense_date"] <= now)
        ]
        kpis["month_expenses"] = m_exp["amount"].sum()
    kpis["net_profit"] = kpis["month_profit"] - kpis["month_expenses"]

    year_start = datetime(now.year, 1, 1)
    year_df    = df[df["sale_date"] >= year_start]
    kpis["year_revenue"] = year_df["total_amount"].sum()
    kpis["year_profit"]  = year_df["gross_profit"].sum()
    kpis["year_txn"]     = len(year_df)

    kpis["alltime_revenue"] = df["total_amount"].sum()
    kpis["alltime_profit"]  = df["gross_profit"].sum()
    kpis["alltime_txn"]     = len(df)

    active_days = df["sale_date"].dt.date.nunique()
    kpis["avg_daily_revenue"] = (
        kpis["alltime_revenue"] / active_days if active_days > 0 else 0
    )

    return kpis


def compute_insights(sales_df, products_df, expenses_df, items_df=None) -> dict:
    """
    Return structured insights dict.
    Called by:  pages/health.py  (insights + export tabs)
                pages/inventory.py (low_stock, stockout_projection)
    items_df: sale_items DataFrame — used for accurate per-product breakdowns.
              Falls back to sales_df if not provided.
    """
    insights = {
        "top_products_revenue":  pd.DataFrame(),
        "top_products_qty":      pd.DataFrame(),
        "slow_movers":           pd.DataFrame(),
        "daily_trend":           pd.DataFrame(),
        "weekday_performance":   pd.DataFrame(),
        "category_revenue":      pd.DataFrame(),
        "low_stock":             pd.DataFrame(),
        "stockout_projection":   pd.DataFrame(),
        "payment_split":         pd.DataFrame(),
        "avg_daily_revenue":     0,
        "best_day":              "",
        "worst_day":             "",
        # Expiry alerts — only populated for products that have expiry_date set
        "expired":               pd.DataFrame(),
        "expiring_soon":         pd.DataFrame(),
    }

    if sales_df.empty:
        return insights

    df = sales_df.dropna(subset=["sale_date"]).copy()

    # Top products — use sale_items for accurate per-product breakdown
    # (sales table stores concatenated names for multi-item sales)
    if items_df is not None and not items_df.empty:
        # Revenue: use line_total per item
        insights["top_products_revenue"] = (
            items_df.groupby("product_name")["line_total"]
            .sum().reset_index()
            .rename(columns={"line_total": "total_amount"})
            .sort_values("total_amount", ascending=False)
            .head(10)
        )
        # Quantity: use quantity per item
        insights["top_products_qty"] = (
            items_df.groupby("product_name")["quantity"]
            .sum().reset_index()
            .sort_values("quantity", ascending=False)
            .head(10)
        )
    else:
        # Fallback to sales_df if items_df not available
        insights["top_products_revenue"] = (
            df.groupby("product_name")["total_amount"]
            .sum().reset_index()
            .sort_values("total_amount", ascending=False)
            .head(10)
        )
        insights["top_products_qty"] = (
            df.groupby("product_name")["quantity"]
            .sum().reset_index()
            .sort_values("quantity", ascending=False)
            .head(10)
        )

    # Daily trend
    df["date"] = df["sale_date"].dt.date
    daily = (
        df.groupby("date")["total_amount"]
        .sum().reset_index().sort_values("date")
    )
    insights["daily_trend"]       = daily
    insights["avg_daily_revenue"] = daily["total_amount"].mean() if not daily.empty else 0

    # Weekday performance
    df["weekday"] = df["sale_date"].dt.day_name()
    wd_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    wd = (
        df.groupby("weekday")["total_amount"]
        .sum().reindex(wd_order, fill_value=0).reset_index()
    )
    wd.columns = ["weekday", "revenue"]
    insights["weekday_performance"] = wd
    if not wd.empty:
        insights["best_day"]  = wd.loc[wd["revenue"].idxmax(), "weekday"]
        insights["worst_day"] = wd.loc[wd["revenue"].idxmin(), "weekday"]

    # Category revenue
    if "category" in df.columns:
        insights["category_revenue"] = (
            df.groupby("category")["total_amount"]
            .sum().reset_index()
            .sort_values("total_amount", ascending=False)
        )

    # Payment split
    if "payment_method" in df.columns:
        insights["payment_split"] = (
            df.groupby("payment_method")["total_amount"].sum().reset_index()
        )

    # Slow movers (last 30 days, below half the average)
    last30 = df[df["sale_date"] >= (datetime.now() - timedelta(days=30))]
    if not last30.empty:
        prod_sales = last30.groupby("product_name")["quantity"].sum().reset_index()
        avg_qty    = prod_sales["quantity"].mean()
        insights["slow_movers"] = (
            prod_sales[prod_sales["quantity"] < avg_qty * 0.5]
            .sort_values("quantity")
        )

    # ── Expiry alerts ─────────────────────────────────────────────────────────
    # Only evaluated for products that have expiry_date set (NaT rows are skipped).
    # Thresholds: expired = past today, expiring_soon = within 60 days.
    _EXPIRY_WARN_DAYS = 60
    if not products_df.empty and "expiry_date" in products_df.columns:
        today      = pd.Timestamp(datetime.now().date())
        dated      = products_df[
            products_df["expiry_date"].notna() &
            (products_df["stock_quantity"] > 0)
        ].copy()
        if not dated.empty:
            dated["days_to_expiry"] = (dated["expiry_date"] - today).dt.days
            expiry_cols = ["product_name", "category", "stock_quantity",
                           "expiry_date", "mfg_date", "days_to_expiry"]
            # Keep only columns that actually exist (mfg_date is also optional)
            expiry_cols = [c for c in expiry_cols if c in dated.columns]
            insights["expired"] = (
                dated[dated["days_to_expiry"] < 0][expiry_cols]
                .sort_values("days_to_expiry")
                .copy()
            )
            insights["expiring_soon"] = (
                dated[
                    (dated["days_to_expiry"] >= 0) &
                    (dated["days_to_expiry"] <= _EXPIRY_WARN_DAYS)
                ][expiry_cols]
                .sort_values("days_to_expiry")
                .copy()
            )

    # Low stock + stockout projection
    if not products_df.empty:
        insights["low_stock"] = products_df[
            products_df["stock_quantity"] <= products_df["reorder_level"]
        ][["product_name","stock_quantity","reorder_level","category"]].copy()

        # Vectorized replacement for the old per-product Python loop: one
        # groupby to get total quantity sold per product, one merge against
        # products_df, then arithmetic over the whole column at once instead
        # of re-scanning the sales dataframe for every single product.
        days_range = max((df["sale_date"].max() - df["sale_date"].min()).days, 1)
        qty_by_product = (
            df.groupby("product_name")["quantity"].sum().reset_index()
            .rename(columns={"quantity": "_qty_sold"})
        )
        proj = products_df[["product_name", "stock_quantity"]].merge(
            qty_by_product, on="product_name", how="inner"
        )
        proj["avg_daily_sales"] = proj["_qty_sold"] / days_range
        proj = proj[proj["avg_daily_sales"] > 0].copy()
        if not proj.empty:
            # Cap at 10 years out. Without this, a corrupted/outlier
            # sale_date (common in cloned/stress-test datasets) can inflate
            # days_range enough to make avg_daily_sales near-zero, which
            # sends days_until_stockout into the hundreds of thousands or
            # millions — enough for datetime.now() + timedelta(days=d) to
            # overflow past year 9999 downstream in inventory.py/health.py.
            _MAX_DAYS_OUT = 3650
            proj["days_until_stockout"] = (
                (proj["stock_quantity"] / proj["avg_daily_sales"])
                .clip(upper=_MAX_DAYS_OUT)
                .round(1)
            )
            proj["avg_daily_sales"] = proj["avg_daily_sales"].round(2)
            insights["stockout_projection"] = (
                proj[["product_name", "stock_quantity",
                      "days_until_stockout", "avg_daily_sales"]]
                .sort_values("days_until_stockout")
            )

    return insights


@st.cache_data(ttl=60, show_spinner=False)
def get_insights_cached(business_id: str) -> dict:
    """
    Cached wrapper around compute_insights(), keyed by business_id with a
    60s TTL. compute_insights() is the heaviest call in the suite (stockout
    projections, slow movers, expiry alerts, etc.) and was previously being
    re-run from scratch on every Streamlit rerun of the page it lives on —
    including every keystroke in a search box on that same page. Caching by
    business_id (a plain string) is cheap to key on, unlike caching directly
    on DataFrame arguments. Stockout/insight numbers being up to 60s stale
    is an acceptable trade for not recomputing on every keystroke.
    """
    sales_df    = get_sales_df(business_id)
    products_df = get_products_df(business_id)
    expenses_df = get_expenses_df(business_id)
    items_df    = get_sale_items_df(business_id)
    return compute_insights(sales_df, products_df, expenses_df, items_df)


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def gen_id(prefix: str = "") -> str:
    """Generate a short unique ID with an optional prefix."""
    return f"{prefix}{uuid.uuid4().hex[:10].upper()}"


def fmt_currency(amount) -> str:
    """Format a number using the current user's currency symbol from session state."""
    try:
        symbol = st.session_state.get("currency_symbol", "₦")
        return f"{symbol}{float(amount):,.2f}"
    except Exception:
        symbol = st.session_state.get("currency_symbol", "₦")
        return f"{symbol}0.00"


# Backward-compatible alias — safe for any existing imports of fmt_naira
fmt_naira = fmt_currency


def safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return default


def fmt_qty(val, decimals: int = 2) -> str:
    """
    Format a stock/quantity number for display, trimming trailing zeros so
    it reads naturally for non-technical users: 18.0 -> "18", 17.50 -> "17.5",
    18.20 -> "18.2" — instead of always showing a fixed "17.50" / "18.00",
    which can look like a typo or confuse users unfamiliar with decimals.
    """
    try:
        num = round(float(val), decimals)
    except Exception:
        return str(val)
    if num == int(num):
        return f"{int(num)}"
    text = f"{num:.{decimals}f}".rstrip("0").rstrip(".")
    return text


def parse_date(val):
    """Parse a date string to datetime. Returns None on failure."""
    try:
        from dateutil import parser as dateparser
        return dateparser.parse(str(val))
    except Exception:
        return None




def validate_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email))
