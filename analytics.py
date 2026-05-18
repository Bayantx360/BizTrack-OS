# ============================================================
#  analytics.py — KPI and insights computation
# ============================================================

import pandas as pd
from datetime import datetime, timedelta


def compute_kpis(sales_df: pd.DataFrame, expenses_df: pd.DataFrame):
    """Return dict of key performance metrics."""
    now   = datetime.now()
    today = now.date()

    kpis = {
        "today_revenue":   0, "week_revenue":    0, "month_revenue":  0,
        "today_profit":    0, "week_profit":     0, "month_profit":   0,
        "today_txn":       0, "week_txn":        0, "month_txn":      0,
        "week_growth":     0, "month_expenses":  0, "net_profit":     0,
        # Extended metrics
        "year_revenue":    0, "year_profit":     0, "year_txn":       0,
        "alltime_revenue": 0, "alltime_profit":  0, "alltime_txn":    0,
        "avg_daily_revenue": 0,
    }

    if sales_df.empty:
        return kpis

    df = sales_df.dropna(subset=["sale_date"])

    # Date buckets
    today_df  = df[df["sale_date"].dt.date == today]
    week_df   = df[df["sale_date"] >= (now - timedelta(days=7))]
    month_df  = df[df["sale_date"] >= (now - timedelta(days=30))]
    prev_week = df[
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

    # Week-on-week growth
    prev_rev = prev_week["total_amount"].sum()
    curr_rev = kpis["week_revenue"]
    if prev_rev > 0:
        kpis["week_growth"] = ((curr_rev - prev_rev) / prev_rev) * 100

    # Expenses & net profit
    if not expenses_df.empty:
        m_exp = expenses_df[expenses_df["expense_date"] >= (now - timedelta(days=30))]
        kpis["month_expenses"] = m_exp["amount"].sum()
    kpis["net_profit"] = kpis["month_profit"] - kpis["month_expenses"]

    # Year-to-date (current calendar year Jan 1 → now)
    year_start = datetime(now.year, 1, 1)
    year_df    = df[df["sale_date"] >= year_start]
    kpis["year_revenue"] = year_df["total_amount"].sum()
    kpis["year_profit"]  = year_df["gross_profit"].sum()
    kpis["year_txn"]     = len(year_df)

    # All-time totals
    kpis["alltime_revenue"] = df["total_amount"].sum()
    kpis["alltime_profit"]  = df["gross_profit"].sum()
    kpis["alltime_txn"]     = len(df)

    # Average daily revenue — total revenue ÷ number of distinct days with sales
    active_days = df["sale_date"].dt.date.nunique()
    kpis["avg_daily_revenue"] = (
        kpis["alltime_revenue"] / active_days if active_days > 0 else 0
    )

    return kpis


def compute_insights(sales_df, products_df, expenses_df):
    """Return structured insights dict for the Insights page."""
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
    }

    if sales_df.empty:
        return insights

    df = sales_df.dropna(subset=["sale_date"]).copy()

    # Top products by revenue
    top_rev = (
        df.groupby("product_name")["total_amount"]
        .sum().reset_index()
        .sort_values("total_amount", ascending=False)
        .head(10)
    )
    insights["top_products_revenue"] = top_rev

    # Top products by quantity
    top_qty = (
        df.groupby("product_name")["quantity"]
        .sum().reset_index()
        .sort_values("quantity", ascending=False)
        .head(10)
    )
    insights["top_products_qty"] = top_qty

    # Daily trend (last 30 days)
    df["date"] = df["sale_date"].dt.date
    daily = (
        df.groupby("date")["total_amount"]
        .sum().reset_index()
        .sort_values("date")
    )
    insights["daily_trend"]        = daily
    insights["avg_daily_revenue"]  = daily["total_amount"].mean() if not daily.empty else 0

    # Weekday performance
    df["weekday"] = df["sale_date"].dt.day_name()
    wd_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    wd = (
        df.groupby("weekday")["total_amount"]
        .sum().reindex(wd_order, fill_value=0)
        .reset_index()
    )
    wd.columns = ["weekday", "revenue"]
    insights["weekday_performance"] = wd
    if not wd.empty:
        insights["best_day"]  = wd.loc[wd["revenue"].idxmax(), "weekday"]
        insights["worst_day"] = wd.loc[wd["revenue"].idxmin(), "weekday"]

    # Category revenue
    if "category" in df.columns:
        cat = (
            df.groupby("category")["total_amount"]
            .sum().reset_index()
            .sort_values("total_amount", ascending=False)
        )
        insights["category_revenue"] = cat

    # Payment split
    if "payment_method" in df.columns:
        pm = df.groupby("payment_method")["total_amount"].sum().reset_index()
        insights["payment_split"] = pm

    # Slow movers (products sold less than average in last 30 days)
    last30 = df[df["sale_date"] >= (datetime.now() - timedelta(days=30))]
    if not last30.empty:
        prod_sales = last30.groupby("product_name")["quantity"].sum().reset_index()
        avg_qty    = prod_sales["quantity"].mean()
        slow       = prod_sales[prod_sales["quantity"] < avg_qty * 0.5].sort_values("quantity")
        insights["slow_movers"] = slow

    # Low stock & stockout projection
    if not products_df.empty:
        low = products_df[
            products_df["stock_quantity"] <= products_df["reorder_level"]
        ][["product_name","stock_quantity","reorder_level","category"]].copy()
        insights["low_stock"] = low

        # Stockout projection: days_left = current_stock / avg_daily_sales
        proj_rows = []
        for _, prod in products_df.iterrows():
            prod_sales_df = df[df["product_name"] == prod["product_name"]]
            if not prod_sales_df.empty:
                days_range  = max((df["sale_date"].max() - df["sale_date"].min()).days, 1)
                avg_per_day = prod_sales_df["quantity"].sum() / days_range
                if avg_per_day > 0:
                    days_left = prod["stock_quantity"] / avg_per_day
                    proj_rows.append({
                        "product_name": prod["product_name"],
                        "stock_quantity": prod["stock_quantity"],
                        "days_until_stockout": round(days_left, 1),
                        "avg_daily_sales": round(avg_per_day, 2),
                    })
        if proj_rows:
            proj_df = pd.DataFrame(proj_rows).sort_values("days_until_stockout")
            insights["stockout_projection"] = proj_df

    return insights
