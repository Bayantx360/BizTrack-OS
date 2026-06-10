"""
suite_home.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Main Entry Point
══════════════════════════════════════════════════════════════════════

Responsibilities:
  1. Initialise session state
  2. Render auth pages (login, signup, forgot password)
  3. Render the sidebar navigation (app switcher + page links)
  4. Route to the correct page module based on session state
  5. Gate every authenticated page behind check_access()

"""

from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="BizTrack-OS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Shared imports ─────────────────────────────────────────────────────────────
from shared.auth import (
    init_session_state, login_user, signup_user,
    sign_out, check_access,
    get_user_by_email, is_subscription_active,
    hash_password,
    SUITE_SESSION_KEYS,
    set_void_pin, has_void_pin,
)
from shared.db import (
    db_update, TBL_USERS,
    PAYMENT_DETAILS, validate_email,
    gen_id, get_supabase,
)
from shared.theme import apply_suite_css

# ── Page module imports ────────────────────────────────────────────────────────
from apps.sales     import page_dashboard, page_record_sale, page_sales_history
from apps.inventory import page_products
from apps.health    import page_expenses, page_insights, page_admin, page_debtors


# ══════════════════════════════════════════════════════════════════════════════
# ROUTING TABLE
# key → (display label, emoji, app_module, render_function)
# ══════════════════════════════════════════════════════════════════════════════
PAGES = {
    # Sales Management
    "dashboard":     ("Dashboard",     "🏠", "sales",     page_dashboard),
    "record_sale":   ("Record Sale",   "🛒", "sales",     page_record_sale),
    "sales_history": ("Sales History", "📋", "sales",     page_sales_history),
    # Inventory Management
    "inventory":     ("Inventory",     "📦", "inventory", page_products),
    # Business Health
    "expenses":      ("Expenses",      "💸", "health",    page_expenses),
    "insights":      ("Insights",      "🧠", "health",    page_insights),
    "debtors":       ("Debtors Ledger","📒", "health",    page_debtors),
    # Admin (conditionally shown)
    "admin":         ("Admin Panel",   "🛡️", "health",    page_admin),
    # Settings
    "settings":      ("Settings",      "⚙️", "settings",  None),
}

APP_META = {
    "sales":     {"label": "Sales Management",     "icon": "💰", "color": "#6366f1"},
    "inventory": {"label": "Inventory Management", "icon": "📦", "color": "#f59e0b"},
    "health":    {"label": "Business Health",      "icon": "🧠", "color": "#10b981"},
}

# Pages grouped by app — controls sidebar rendering order
APP_PAGES = {
    "sales":     ["dashboard", "record_sale", "sales_history"],
    "inventory": ["inventory"],
    "health":    ["expenses", "insights", "debtors"],
}


# ══════════════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def get_business_social_proof():
    """Return (count, [first 4 business name initials]) — cached 5 min."""
    try:
        sb   = get_supabase()
        res  = sb.table(TBL_USERS).select("business_name", count="exact").execute()
        count = res.count or 0
        names = [
            (r.get("business_name") or "B").strip().upper()[0]
            for r in (res.data or [])
            if (r.get("business_name") or "").strip()
        ]
        return count, names[:4]
    except Exception:
        return 0, []


def page_login():
    apply_suite_css()
    st.markdown("""
<div class="lp-hero">
  <div class="lp-logo-wrap">
    <div class="lp-logo-icon">📊</div>
  </div>
  <div class="lp-logo-text">BizTrack-OS</div><br>
  <div class="lp-badge"><span>●</span> All-in-one business suite</div>
  <div class="lp-headline">Run & Monitor your <span>Business</span><br>Smarter</div>
  <div class="lp-sub">
    💰Record your Daily Sales & Revenue ● 📦Track your Inventory Stock Level ● 📈Monitor your Business Growth—  All in one place on BizTrack-OS
  </div>
  <div class="lp-value-grid">
    <div class="lp-value-card">
      <div class="lp-value-icon">💰</div>
      <div class="lp-value-title">Sales Management</div>
      <div class="lp-value-desc">Record sales with multi-item carts,
        instantly generate PDF receipts and share on WhatsApp.</div>
    </div>
    <div class="lp-value-card">
      <div class="lp-value-icon">📦</div>
      <div class="lp-value-title">Inventory Control</div>
      <div class="lp-value-desc">Live stock levels, reorder alerts and
        automatic stockout projections.</div>
    </div>
    <div class="lp-value-card">
      <div class="lp-value-icon">🧠</div>
      <div class="lp-value-title">Business Health</div>
      <div class="lp-value-desc">Profit/loss, expenses, trend charts and
        Data-driven insights — all in one view.</div>
    </div>
  </div>
</div>
    """, unsafe_allow_html=True)

    # ── Social proof — shop icon avatars + named businesses ──
    TRUSTED_BUSINESSES = [
        {"name": "Rabz Pharma",      "color": "E8F4FD", "fg": "1A6FA8"},
        {"name": "Ammy's Gadgets",   "color": "CFFAFE", "fg": "0E7490"},
        {"name": "Bara Ventures",     "color": "FEF3C7", "fg": "A07A10"},
        {"name": "Obantz Ltd",  "color": "FDEDEC", "fg": "A83228"},
        {"name": "Bularis C.E",  "color": "EDE9FE", "fg": "6D28D9"},
        {"name": "Tundsam Agromart Ltd",   "color": "D1FAE5", "fg": "065F46"},
        {"name": "Omokorewa Kitchen Utensils",   "color": "FFF7ED", "fg": "C2410C"},
    ]
    # shop SVG icon — same for all, colour changes per avatar
    def shop_avatar(bg, fg):
        return (
            f'<div style="width:36px;height:36px;border-radius:50%;'
            f'background:#{bg};border:2px solid #1a1a2e;flex-shrink:0;'
            f'display:flex;align-items:center;justify-content:center;'
            f'margin-right:-10px;position:relative;" title="">'
            f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M3 9l1-5h16l1 5" stroke="#{fg}" stroke-width="1.8" '
            f'stroke-linecap="round"/>'
            f'<path d="M3 9h18v11a1 1 0 01-1 1H4a1 1 0 01-1-1V9z" '
            f'stroke="#{fg}" stroke-width="1.8"/>'
            f'<path d="M9 21v-6h6v6" stroke="#{fg}" stroke-width="1.8" '
            f'stroke-linecap="round"/>'
            f'</svg></div>'
        )
    
    avatars_html = "".join(
        shop_avatar(b["color"], b["fg"]) for b in TRUSTED_BUSINESSES
    )
    names_str = ", ".join(b["name"] for b in TRUSTED_BUSINESSES[:-1])
    names_str += f", {TRUSTED_BUSINESSES[-1]['name']}"

    biz_count, _ = get_business_social_proof()
    label = "Business" if biz_count == 1 else "Businesses"
    count_display = biz_count if biz_count > 0 else len(TRUSTED_BUSINESSES)

    st.markdown(f"""
<div style="display:flex;flex-direction:column;align-items:center;
            gap:10px;padding:18px 0 8px;">
  <div style="display:flex;align-items:center;justify-content:center;">
    {avatars_html}
    <div style="width:36px;height:36px;border-radius:50%;
                background:#2A2A3E;border:2px solid #1a1a2e;flex-shrink:0;
                display:flex;align-items:center;justify-content:center;
                font-size:11px;font-weight:600;color:#A0A8C0;margin-right:10px;">
      +{max(0, count_display - len(TRUSTED_BUSINESSES))}
    </div>
    <div style="font-size:13px;color:#10B981;line-height:1.4;">
      <strong style="color:#EAB308;">{count_display} {label}</strong>
      already running on <strong style="color:#EAB308;">BizTrack-OS</strong>
    </div>
  </div>
  <div style="font-size:11.5px;color:#6B7280;text-align:center;
              line-height:1.6;max-width:340px;">
    Trusted by <span style="color:#D1D5DB;">{names_str}</span> and more amazing businesses 🇳🇬.
  </div>
</div>
    """, unsafe_allow_html=True)

    _, form_col, _ = st.columns([1, 1.4, 1])
    with form_col:
        st.markdown('<div class="lp-divider">Sign in to your account</div>',
                    unsafe_allow_html=True)
        with st.form("login_form"):
            email    = st.text_input("Email address", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submit   = st.form_submit_button("Sign In →", type="primary",
                                             width='stretch')
        if submit:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                ok, user, msg = login_user(email.strip().lower(), password)
                if ok:
                    # Check forced password change
                    if user.get("must_change_password") == "yes":
                        st.session_state.force_pw_change_user = user
                        st.session_state.current_page         = "force_password_change"
                        st.rerun()
                    else:
                        st.session_state.logged_in    = True
                        st.session_state.user         = user
                        st.session_state.current_page = "dashboard"
                        st.rerun()
                else:
                    st.error(msg)

        st.markdown('<div class="lp-divider"> Register New Account/Reset Password</div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("Create account", width='stretch', type="primary"):
            st.session_state.current_page = "signup"; st.rerun()
        if c2.button("Forgot password?", width='stretch', type="primary"):
            st.session_state.current_page = "forgot_password"; st.rerun()

        st.markdown("""
<div class="lp-trust-strip">
  <span class="lp-trust-item"><span>🔒</span> Password secured login</span>
  <span class="lp-trust-item"><span>☁️</span> Data backed on cloud daily</span>
  <span class="lp-trust-item"><span>📱</span> Works on mobile phones </span>
  <span class="lp-trust-item"><span>🏣</span> Built for all SMEs</span>
</div>

<div style="
  margin-top:2rem;
  padding-top:1.25rem;
  text-align:center;
">
  <div style="font-size:0.72rem;color:#4A6080;margin-bottom:0.75rem;
    font-family:'DM Mono',monospace;letter-spacing:0.05em;">
    For Issues & Enquiries<br>Contact Us:
  </div>
  <div style="display:flex;justify-content:center;gap:1.25rem;flex-wrap:wrap;">
    <a href="https://facebook.com/Bayantx360"
       target="_blank"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#0a1020;border:1px solid #1877F2;
         color:#1877F2;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>📱</span> Facebook
    </a>
    <a href="https://wa.me/+2348136362633"
       target="_blank"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#0a2a1e;border:1px solid #00C896;
         color:#00C896;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>💬</span> WhatsApp
    </a>
    <a href="https://twitter.com/Bayantx360"
       target="_blank"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#0a1525;border:1px solid #1d9bf0;
         color:#1d9bf0;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>𝕏</span> Twitter
    </a>
    <a href="mailto:Bayantx360@gmail.com"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#1a1025;border:1px solid #F5A623;
         color:#F5A623;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>📧</span> Email
    </a>
  </div>
  <div style="margin-top:1.25rem;font-size:0.68rem;color:#2D3F55;">
    © 2026 BizTrack-OS: Powered by Bayantx360 · All rights reserved
  </div>
</div>
        """, unsafe_allow_html=True)


def page_signup():
    apply_suite_css()
    _, col, _ = st.columns([1, 1.6, 1])
    with col:
        st.markdown("""
<div style="text-align:center;margin-bottom:1.5rem;">
  <div style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;
    color:#F0F4F8;letter-spacing:-0.04em;">Create your account</div>
  <div style="font-size:0.85rem;color:#22C55E;margin-top:0.3rem;">
    Start with a 14-day free trial. No credit card required.</div>
</div>
        """, unsafe_allow_html=True)

        with st.form("signup_form"):
            biz_name  = st.text_input("Business Name *",  placeholder="e.g. BigBay Gadget")
            full_name = st.text_input("Your Full Name *",  placeholder="e.g. Emeka Atanda Salisu")
            phone     = st.text_input("Phone Number *",    placeholder="e.g. 08012345678")
            email     = st.text_input("Email Address *",   placeholder="you@example.com")
            password  = st.text_input("Password *",        type="password",
                                      placeholder="At least 6 characters")
            st.markdown("##### Choose a plan")
            plan_type = st.radio(
                "Plan",
                options=["trial", "monthly", "yearly"],
                format_func=lambda p: {
                    "trial":   f"🎁 Free Trial — 14 days, no payment needed",
                    "monthly": f"📅 Monthly — ₦{PAYMENT_DETAILS['monthly_price']:,}/month",
                    "yearly":  f"🏆 Yearly — ₦{PAYMENT_DETAILS['yearly_price']:,}/year (save ₦3,000)",
                }[p],
                horizontal=False,
            )
            submit = st.form_submit_button("Create Account →", type="primary",
                                           width='stretch')

        if submit:
            if not all([biz_name, full_name, phone, email, password]):
                st.error("Please fill in all required fields.")
            else:
                with st.spinner("Creating your account…"):
                    ok, msg = signup_user(biz_name.strip(), full_name.strip(),
                                          email.strip().lower(), phone.strip(), password, plan_type)
                if ok:
                    if plan_type == "trial":
                        user_obj = get_user_by_email(email.strip().lower())
                        if user_obj:
                            st.session_state.logged_in    = True
                            st.session_state.user         = user_obj
                            st.session_state.current_page = "dashboard"
                            st.rerun()
                    else:
                        user_obj = get_user_by_email(email.strip().lower())
                        if user_obj:
                            st.session_state.logged_in    = True
                            st.session_state.user         = user_obj
                        st.session_state.pending_email = email.strip().lower()
                        st.session_state.pending_plan  = plan_type
                        st.session_state.current_page  = "pending_payment"
                        st.rerun()
                else:
                    st.error(msg)

        st.markdown("---")
        if st.button("← Already have an account? Sign in", width='stretch'):
            st.session_state.current_page = "login"; st.rerun()


def page_forgot_password():
    apply_suite_css()
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
<div style="text-align:center;margin-bottom:1.5rem;">
  <div style="font-size:2.5rem;">🔑</div>
  <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;
    color:#F0F4F8;">Reset your password</div>
  <div style="font-size:0.85rem;color:#4A6080;margin-top:0.3rem;">
    Your admin will set a temporary password for you.</div>
</div>
        """, unsafe_allow_html=True)

        with st.form("forgot_form"):
            email  = st.text_input("Email address", placeholder="you@example.com")
            submit = st.form_submit_button("Request Reset", type="primary",
                                           width='stretch')
        if submit:
            if not email:
                st.error("Please enter your email address.")
            else:
                user = get_user_by_email(email.strip().lower())
                if user:
                    db_update(TBL_USERS, "user_id", user["user_id"], {
                        "password_reset_requested": "yes",
                        "reset_requested_at":       datetime.now().isoformat(),
                    })
                    st.success(
                        "✅ Reset request submitted. Your admin will provide a temporary "
                        "password to complete your Reset shortly."
                    )
                else:
                    st.info("If that email is registered, a reset request has been submitted.")

        st.markdown("---")
        if st.button("← Back to Sign In", width='stretch'):
            st.session_state.current_page = "login"; st.rerun()


def page_force_password_change():
    """Shown when must_change_password == 'yes' (after an admin reset)."""
    apply_suite_css()
    user = st.session_state.get("force_pw_change_user", {})
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
<div style="text-align:center;margin-bottom:1.5rem;">
  <div style="font-size:2rem;">🔐</div>
  <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;color:#F0F4F8;">
    Set a new password</div>
  <div style="font-size:0.85rem;color:#4A6080;margin-top:0.3rem;">
    🔐Your password reset is being processed safely. Please choose a new one before continuing.</div>
</div>
        """, unsafe_allow_html=True)
        with st.form("force_pw_form"):
            new_pw  = st.text_input("New password",     type="password", placeholder="At least 6 characters")
            conf_pw = st.text_input("Confirm password", type="password", placeholder="Repeat new password")
            submit  = st.form_submit_button("Update Password →", type="primary",
                                            width='stretch')
        if submit:
            if len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != conf_pw:
                st.error("Passwords do not match.")
            elif not user:
                st.error("Session expired. Please log in again.")
                st.session_state.current_page = "login"; st.rerun()
            else:
                db_update(TBL_USERS, "user_id", user["user_id"], {
                    "password_hash":        hash_password(new_pw),
                    "must_change_password": "no",
                })
                st.session_state.logged_in    = True
                st.session_state.user         = {**user, "must_change_password": "no"}
                st.session_state.current_page = "dashboard"
                st.session_state.pop("force_pw_change_user", None)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    user         = st.session_state.get("user", {})
    current_page = st.session_state.get("current_page", "dashboard")
    is_admin     = user.get("role") == "admin"

    with st.sidebar:
        # ── Logo ──
        st.markdown("""
<div style="display:flex;align-items:center;gap:0.6rem;padding:0.75rem 0 1.25rem;">
  <div style="
    width:40px;height:40px;border-radius:10px;
    background:linear-gradient(135deg,#F5A623,#C4831A);
    display:flex;align-items:center;justify-content:center;
    font-size:1.2rem;box-shadow:0 4px 16px rgba(245,166,35,0.3);
    flex-shrink:0;
  ">📊</div>
  <div>
    <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;
      color:#F0F4F8;letter-spacing:-0.03em;line-height:1;">BizTrack-OS</div>
    <div style="font-size:0.65rem;color:#4A6080;font-family:'DM Mono',monospace;
      letter-spacing:0.05em;">SUITE</div>
  </div>
</div>
        """, unsafe_allow_html=True)

        # ── Business info ──
        biz_name  = user.get("business_name","")
        plan_type = user.get("plan_type","").capitalize()
        plan_end  = user.get("subscription_end","")
        try:
            end_dt    = datetime.strptime(str(plan_end)[:10], "%Y-%m-%d")
            days_left = (end_dt - datetime.now()).days
            expiry_str = f"Expires {end_dt.strftime('%d %b %Y')}"
            if days_left <= 7 and not is_admin:
                expiry_str = f"⚠️ {days_left}d left"
        except Exception:
            expiry_str = ""

        st.markdown(f"""
<div style="background:#111827;border:1px solid #1F2D3D;border-radius:10px;
  padding:0.75rem 0.875rem;margin-bottom:1rem;">
  <div style="font-size:0.78rem;font-weight:700;color:#F0F4F8;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    margin-bottom:0.2rem;">{biz_name}</div>
  <div style="font-size:0.68rem;color:#4A6080;font-family:'DM Mono',monospace;">
    {plan_type} {'· ' + expiry_str if expiry_str else ''}</div>
</div>
        """, unsafe_allow_html=True)

        # ── App switcher + page links ──
        pages_to_show = {**APP_PAGES}
        if is_admin:
            pages_to_show["health"] = ["expenses", "insights", "admin"]

        for app_key, page_keys in pages_to_show.items():
            meta = APP_META[app_key]
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:0.4rem;
  margin:0.875rem 0 0.375rem;
  padding-bottom:0.35rem;border-bottom:1px solid #1F2D3D;">
  <span style="font-size:0.9rem;">{meta['icon']}</span>
  <span style="font-size:0.65rem;font-weight:700;color:#4A6080;
    text-transform:uppercase;letter-spacing:0.12em;
    font-family:'DM Mono',monospace;">{meta['label']}</span>
</div>
            """, unsafe_allow_html=True)

            for page_key in page_keys:
                label, emoji, _, _ = PAGES[page_key]
                is_active           = current_page == page_key
                btn_style = (
                    "background:rgba(245,166,35,0.12);border:1px solid rgba(245,166,35,0.3);"
                    "color:#F5A623;"
                    if is_active else
                    "background:transparent;border:1px solid transparent;color:#8BA0B8;"
                )
                btn_html = f"""
<button onclick="window.parent.postMessage({{type:'streamlit:setComponentValue',
  value:'{page_key}'}}, '*')"
  style="width:100%;text-align:left;padding:0.45rem 0.7rem;
    border-radius:8px;cursor:pointer;font-size:0.82rem;font-weight:600;
    margin-bottom:3px;transition:all 0.15s;{btn_style}">
  {emoji} {label}
</button>
                """
                # Use native Streamlit buttons for reliable routing
                btn_clicked = st.button(
                    f"{emoji} {label}",
                    key=f"nav_{page_key}",
                    width='stretch',
                    type="primary" if is_active else "secondary",
                )
                if btn_clicked:
                    st.session_state.current_page = page_key
                    st.rerun()

        # ── Settings + Sign out ──
        st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        is_settings = current_page == "settings"
        if st.button(
            "⚙️ Settings",
            key="nav_settings",
            width="stretch",
            type="primary" if is_settings else "secondary",
        ):
            st.session_state.current_page = "settings"
            st.rerun()
        if st.button("⎋ Sign Out", width='stretch'):
            sign_out()
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ══════════════════════════════════════════════════════════════════════════════

def page_settings():
    from shared.theme import page_header, section_header
    from shared.auth import set_void_pin, has_void_pin
    apply_suite_css()
    page_header("⚙️ Settings", "Manage your account and security preferences")

    user    = st.session_state.get("user", {})
    user_id = user.get("user_id", "")

    section_header("🔐 Void PIN")
    st.markdown(
        "The Void PIN protects sale records from being deleted. "
        "Only someone who knows this PIN can void a transaction from Sales History."
    )

    pin_set = has_void_pin(user)
    if pin_set:
        st.success("✅ Void PIN is active.")
    else:
        st.warning("⚠️ No Void PIN set — anyone can currently void sales. Set one below.")

    action = st.radio(
        "Action",
        ["Set / Change PIN", "Remove PIN"] if pin_set else ["Set PIN"],
        horizontal=True,
        key="pin_action",
    )

    if action == "Set PIN":
        # ── First-time setup — no existing PIN to verify ──────────────
        with st.form("set_pin_form", clear_on_submit=True):
            new_pin     = st.text_input("New PIN (4–12 characters)",
                                         type="password",
                                         placeholder="Letters, numbers or symbols")
            confirm_pin = st.text_input("Confirm PIN", type="password")
            submitted   = st.form_submit_button("💾 Save PIN", type="primary")

        if submitted:
            if new_pin != confirm_pin:
                st.error("PINs do not match.")
            else:
                ok, msg = set_void_pin(user_id, new_pin)
                if ok:
                    updated = get_user_by_email(user.get("email", ""))
                    if updated:
                        st.session_state.user = updated
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    elif action == "Set / Change PIN":
        # ── Change flow — must prove knowledge of the current PIN first ──
        st.info("🔐 You must enter your **current PIN** before setting a new one.")
        with st.form("change_pin_form", clear_on_submit=True):
            current_pin = st.text_input("Current PIN",
                                         type="password",
                                         placeholder="Your existing PIN")
            st.markdown("---")
            new_pin     = st.text_input("New PIN (4–12 characters)",
                                         type="password",
                                         placeholder="Letters, numbers or symbols")
            confirm_pin = st.text_input("Confirm New PIN", type="password")
            submitted   = st.form_submit_button("💾 Update PIN", type="primary")

        if submitted:
            from shared.auth import verify_void_pin
            if not verify_void_pin(user, current_pin):
                st.error("❌ Incorrect current PIN. PIN not changed.")
            elif new_pin != confirm_pin:
                st.error("New PINs do not match.")
            elif new_pin == current_pin:
                st.error("New PIN must be different from your current PIN.")
            else:
                ok, msg = set_void_pin(user_id, new_pin)
                if ok:
                    updated = get_user_by_email(user.get("email", ""))
                    if updated:
                        st.session_state.user = updated
                    st.success("✅ Void PIN updated successfully.")
                    st.rerun()
                else:
                    st.error(msg)

    elif action == "Remove PIN":
        st.info("Removing the PIN means anyone can void sales without restriction.")
        with st.form("remove_pin_form"):
            current_pin = st.text_input("Enter current PIN to confirm removal",
                                         type="password")
            remove_btn  = st.form_submit_button("🗑️ Remove PIN", type="primary")
        if remove_btn:
            from shared.auth import verify_void_pin
            if verify_void_pin(user, current_pin):
                ok = db_update(TBL_USERS, "user_id", user_id, {"void_pin_hash": None})
                if ok:
                    updated = get_user_by_email(user.get("email", ""))
                    if updated:
                        st.session_state.user = updated
                    st.success("Void PIN removed.")
                    st.rerun()
                else:
                    st.error("Failed to remove PIN.")
            else:
                st.error("Incorrect PIN.")


def main():
    init_session_state()

    current_page = st.session_state.get("current_page", "login")
    logged_in    = st.session_state.get("logged_in", False)

    # ── Unauthenticated routes ─────────────────────────────────────────────────
    if not logged_in:
        route_map = {
            "login":           page_login,
            "signup":          page_signup,
            "forgot_password": page_forgot_password,
            "force_password_change": page_force_password_change,
            "pending_payment": lambda: __import__(
                "shared.auth", fromlist=["_page_pending_payment"]
            )._page_pending_payment(st.session_state.get("user", {})),
        }
        fn = route_map.get(current_page, page_login)
        fn()
        return

    # ── Authenticated routes ───────────────────────────────────────────────────
    render_sidebar()

    # Subscription guard — exits early if pending / expired
    if not check_access():
        return

    # Dispatch to page render function
    if current_page == "settings":
        page_settings()
    else:
        page_entry = PAGES.get(current_page)
        if page_entry:
            _, _, _, render_fn = page_entry
            render_fn()
        else:
            # Fallback to dashboard
            st.session_state.current_page = "dashboard"
            page_dashboard()


if __name__ == "__main__":
    # ── Branded splash to mask the initial Streamlit render flash ──
    if not st.session_state.get("_splash_done"):
        splash = st.empty()
        splash.markdown("""
<style>
.splash-wrap {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 80vh; gap: 1rem;
}
.splash-icon {
    width: 72px; height: 72px; border-radius: 18px;
    background: linear-gradient(135deg, #F5A623, #C4831A);
    display: flex; align-items: center; justify-content: center;
    font-size: 2rem;
    box-shadow: 0 8px 32px rgba(245,166,35,0.35);
}
.splash-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.8rem; font-weight: 800;
    color: #F0F4F8; letter-spacing: -0.03em;
}
.splash-sub {
    font-size: 0.8rem; color: #4A6080;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.1em; text-transform: uppercase;
}
</style>
<div class="splash-wrap">
  <div class="splash-icon">📊</div>
  <div class="splash-title">BizTrack-OS</div>
  <div class="splash-sub">Loading your suite…</div>
</div>
        """, unsafe_allow_html=True)
        st.session_state["_splash_done"] = True
        st.rerun()
    else:
        main()
