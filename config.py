# ============================================================
#  config.py — Constants, table names, plan pricing
# ============================================================

# Supabase table names
TBL_USERS      = "users"
TBL_PRODUCTS   = "products"
TBL_SALES      = "sales"
TBL_EXPENSES   = "expenses"
TBL_PAYMENTS   = "payments"
TBL_RESTOCK    = "restock_log"
TBL_SALE_ITEMS = "sale_items"

# Plan pricing & Flutterwave links
PAYMENT_DETAILS = {
    "monthly_price":       1500,
    "yearly_price":        15000,
    "trial_days":          14,
    "flutterwave_monthly": "https://flutterwave.com/pay/YOUR_MONTHLY_LINK",
    "flutterwave_yearly":  "https://flutterwave.com/pay/YOUR_YEARLY_LINK",
}
