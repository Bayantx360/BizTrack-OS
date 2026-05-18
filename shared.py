# ============================================================
#  shared.py — Single import hub for all view modules
# ============================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from config import (
    TBL_USERS, TBL_PRODUCTS, TBL_SALES, TBL_EXPENSES,
    TBL_PAYMENTS, TBL_RESTOCK, TBL_SALE_ITEMS, PAYMENT_DETAILS,
)
from db import (
    db_fetch, db_insert, db_update, db_delete,
    get_sales_df, get_products_df, get_expenses_df,
    get_payments_df, log_payment, get_supabase,
)
from utils import (
    gen_id, fmt_naira, safe_float, safe_int,
    kpi_card, section_header, page_header, stock_pill,
    validate_email, parse_date,
)
from analytics import compute_kpis, compute_insights
from auth import (
    get_user_by_email, hash_password, check_password,
    signup_user, login_user, is_subscription_active,
)
from styles import inject_styles, inject_sidebar_toggle
