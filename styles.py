# ============================================================
#  styles.py — Global CSS injection and sidebar toggle
# ============================================================

import streamlit as st


def inject_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=DM+Mono:wght@400;500&display=swap');

/* ── CSS Variables ── */
:root {
--obsidian:    #080B0F;
--deep:        #0D1117;
--surface:     #111827;
--surface2:    #1A2332;
--border:      #1F2D3D;
--border2:     #2D3F55;
--gold:        #F5A623;
--gold-dim:    #C4831A;
--gold-glow:   rgba(245,166,35,0.15);
--jade:        #00C896;
--jade-dim:    rgba(0,200,150,0.12);
--ruby:        #FF4D6D;
--ruby-dim:    rgba(255,77,109,0.12);
--text-primary: #F0F4F8;
--text-secondary: #8BA0B8;
--text-muted:   #4A6080;
--font-display: 'Syne', sans-serif;
--font-body:    'DM Sans', sans-serif;
--font-mono:    'DM Mono', monospace;
}

/* ── Base Reset ── */
html, body, [class*="css"], .stApp {
font-family: var(--font-body);
background-color: var(--deep) !important;
color: var(--text-primary);
}
#MainMenu, footer { visibility: hidden; }

/* Keep header and ALL its children fully visible — sidebar toggle lives here */
header, [data-testid="stHeader"] {
background:  rgba(8,11,15,0.95) !important;
visibility:  visible !important;
display:     flex    !important;
opacity:     1       !important;
z-index:     999990  !important;
backdrop-filter: blur(8px);
border-bottom: 1px solid #1F2D3D;
}
/* Do NOT hide the toolbar — it contains the sidebar toggle button */
header [data-testid="stToolbar"],
[data-testid="stHeader"] [data-testid="stToolbar"] {
visibility:  visible !important;
display:     flex    !important;
opacity:     1       !important;
}

/* Ensure every possible Streamlit sidebar toggle selector is visible */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarToggle"],
[data-testid="stSidebarToggleButton"],
button[aria-label="Open sidebar"],
button[aria-label="Close sidebar"],
button[aria-label="collapse sidebar"],
button[aria-label="expand sidebar"] {
display:        flex   !important;
visibility:     visible !important;
opacity:        1      !important;
pointer-events: auto   !important;
}

/* Custom sidebar tab injected by JS below */
#bpSidebarTab {
position: fixed;
top: 50vh;
left: 0;
transform: translateY(-50%);
z-index: 999999;
background: #111827;
border: 1px solid #2D3F55;
border-left: none;
border-radius: 0 10px 10px 0;
padding: 0.6rem 0.45rem;
cursor: pointer;
box-shadow: 4px 0 16px rgba(0,0,0,0.5);
display: flex;
align-items: center;
justify-content: center;
transition: background 0.15s, border-color 0.15s;
}
#bpSidebarTab:hover { background:#1A2332; border-color:#F5A623; }
#bpSidebarTab svg   { width:18px; height:18px; fill:#F5A623; }
.block-container {
padding-top: 1.5rem !important;
padding-bottom: 3rem !important;
max-width: 1280px;
}

/* ── Mobile Responsive ── */
@media (max-width: 768px) {
.block-container {
padding-left: 0.75rem !important;
padding-right: 0.75rem !important;
padding-top: 0.75rem !important;
}
.kpi-card { padding: 1rem 1.1rem; margin-bottom: 0.6rem; }
.kpi-value { font-size: 1.4rem; }
.pricing-grid { flex-direction: column; align-items: center; }
.pricing-card { max-width: 100%; min-width: unset; width: 100%; }
.pricing-card.featured { transform: translateY(0); }
[data-testid="stSidebar"] { width: 240px !important; }
.login-value-grid {
grid-template-columns: 1fr 1fr !important;
gap: 0.6rem !important;
}
.login-feature-strip {
flex-direction: column !important;
gap: 0.5rem !important;
}
}
@media (max-width: 480px) {
.kpi-value { font-size: 1.2rem; }
.login-value-grid { grid-template-columns: 1fr 1fr !important; }
}

/* ── Streamlit input overrides ── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div,
.stDateInput > div > div > input,
.stTextArea textarea {
background: var(--surface) !important;
border: 1px solid var(--border2) !important;
border-radius: 10px !important;
color: var(--text-primary) !important;
font-family: var(--font-body) !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea textarea:focus {
border-color: var(--gold) !important;
box-shadow: 0 0 0 3px var(--gold-glow) !important;
}
label, .stRadio label, .stCheckbox label {
color: var(--text-secondary) !important;
font-family: var(--font-body) !important;
font-size: 0.85rem !important;
font-weight: 500 !important;
}
.stRadio > div { gap: 0.5rem; }

/* ── KPI Cards ── */
.kpi-card {
background: var(--surface);
border: 1px solid var(--border);
border-radius: 16px;
padding: 1.4rem 1.6rem;
color: var(--text-primary);
margin-bottom: 1rem;
position: relative;
overflow: hidden;
transition: border-color 0.2s, transform 0.2s;
}
.kpi-card::before {
content: '';
position: absolute;
top: 0; left: 0; right: 0;
height: 2px;
background: linear-gradient(90deg, var(--gold), transparent);
opacity: 0.6;
}
.kpi-card:hover {
border-color: var(--border2);
transform: translateY(-2px);
}
.kpi-label {
font-size: 0.7rem;
font-weight: 600;
letter-spacing: 0.12em;
text-transform: uppercase;
color: var(--text-muted);
margin-bottom: 0.5rem;
font-family: var(--font-body);
}
.kpi-value {
font-size: 1.85rem;
font-weight: 700;
color: var(--text-primary);
font-family: var(--font-mono);
line-height: 1.1;
letter-spacing: -0.02em;
}
.kpi-sub {
font-size: 0.75rem;
color: var(--text-muted);
margin-top: 0.4rem;
font-family: var(--font-body);
}
.kpi-positive { color: var(--jade) !important; }
.kpi-negative { color: var(--ruby) !important; }

/* ── Alert Cards ── */
.alert-low {
background: rgba(245,166,35,0.08);
border: 1px solid rgba(245,166,35,0.25);
border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;
color: #F5A623; font-size: 0.85rem;
}
.alert-critical {
background: var(--ruby-dim);
border: 1px solid rgba(255,77,109,0.3);
border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;
color: #FF4D6D; font-size: 0.85rem;
}
.alert-success {
background: var(--jade-dim);
border: 1px solid rgba(0,200,150,0.3);
border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;
color: var(--jade); font-size: 0.85rem;
}

/* ── Section Headers ── */
.section-header {
font-size: 1rem; font-weight: 700;
font-family: var(--font-display);
color: var(--text-primary);
margin: 1.75rem 0 0.875rem 0;
padding-bottom: 0.5rem;
border-bottom: 1px solid var(--border);
letter-spacing: -0.01em;
}

/* ── Page Title ── */
.page-title {
font-size: 1.75rem; font-weight: 800;
font-family: var(--font-display);
color: var(--text-primary);
margin-bottom: 0.2rem;
letter-spacing: -0.03em;
}
.page-subtitle {
font-size: 0.875rem;
color: var(--text-secondary);
margin-bottom: 1.5rem;
}

/* ── Auth Card ── */
.auth-card {
max-width: 480px; margin: 2rem auto;
background: var(--surface);
border-radius: 20px;
padding: 2.5rem;
box-shadow: 0 32px 80px rgba(0,0,0,0.5), 0 0 0 1px var(--border);
border: 1px solid var(--border2);
}
.auth-logo {
font-size: 1.75rem; font-weight: 800;
font-family: var(--font-display);
color: var(--text-primary);
text-align: center; margin-bottom: 0.25rem;
letter-spacing: -0.04em;
}
.auth-tagline {
text-align: center;
color: var(--text-muted);
font-size: 0.85rem; margin-bottom: 2rem;
}

/* ── Auth form wrap ── */
.auth-form-wrap {
max-width: 480px; margin: 0 auto;
background: var(--surface);
border-radius: 20px;
padding: 2.5rem;
box-shadow: 0 32px 80px rgba(0,0,0,0.5);
border: 1px solid var(--border2);
}

/* ── Stock Status Pills ── */
.stock-ok      { background:var(--jade-dim); color:var(--jade); padding:3px 10px; border-radius:99px; font-size:0.72rem; font-weight:600; border:1px solid rgba(0,200,150,0.2); }
.stock-low     { background:rgba(245,166,35,0.1); color:var(--gold); padding:3px 10px; border-radius:99px; font-size:0.72rem; font-weight:600; border:1px solid rgba(245,166,35,0.2); }
.stock-critical { background:var(--ruby-dim); color:var(--ruby); padding:3px 10px; border-radius:99px; font-size:0.72rem; font-weight:600; border:1px solid rgba(255,77,109,0.2); }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
background: var(--obsidian) !important;
border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * {
color: var(--text-secondary) !important;
font-family: var(--font-body) !important;
}
[data-testid="stSidebar"] .stButton > button {
background: transparent !important;
border: 1px solid var(--border) !important;
color: var(--text-secondary) !important;
text-align: left !important;
border-radius: 10px !important;
font-weight: 500 !important;
transition: all 0.15s !important;
padding: 0.6rem 1rem !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
border-color: var(--gold) !important;
color: var(--gold) !important;
background: var(--gold-glow) !important;
}

/* ── Buttons ── */
.stButton > button {
border-radius: 10px !important;
font-weight: 600 !important;
font-family: var(--font-body) !important;
transition: all 0.2s !important;
letter-spacing: 0.01em !important;
}
.stButton > button[kind="primary"] {
background: var(--gold) !important;
border: none !important;
color: #080B0F !important;
font-weight: 700 !important;
box-shadow: 0 4px 20px rgba(245,166,35,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
background: #FFB83F !important;
box-shadow: 0 6px 28px rgba(245,166,35,0.5) !important;
transform: translateY(-1px) !important;
}
.stLinkButton > a {
background: var(--gold) !important;
color: #080B0F !important;
font-weight: 700 !important;
border-radius: 10px !important;
border: none !important;
box-shadow: 0 4px 20px rgba(245,166,35,0.35) !important;
}
.stLinkButton > a:hover {
background: #FFB83F !important;
box-shadow: 0 6px 28px rgba(245,166,35,0.5) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
background: var(--surface) !important;
border-radius: 12px !important;
border: 1px solid var(--border) !important;
padding: 4px !important;
gap: 2px !important;
}
.stTabs [data-baseweb="tab"] {
background: transparent !important;
color: var(--text-muted) !important;
border-radius: 8px !important;
font-family: var(--font-body) !important;
font-weight: 500 !important;
font-size: 0.82rem !important;
}
.stTabs [aria-selected="true"] {
background: var(--surface2) !important;
color: var(--gold) !important;
border: 1px solid var(--border2) !important;
}
.stTabs [data-baseweb="tab-panel"] {
padding-top: 1.25rem !important;
}

/* ── Metrics / dataframes ── */
[data-testid="stMetricValue"] {
color: var(--text-primary) !important;
font-family: var(--font-mono) !important;
}
.stDataFrame {
border: 1px solid var(--border) !important;
border-radius: 12px !important;
overflow: hidden;
}

/* ── Dividers ── */
hr { border-color: var(--border) !important; }

/* ── Pricing Cards ── */
.pricing-grid {
display: flex; gap: 1.25rem;
justify-content: center;
flex-wrap: wrap; margin: 2rem 0;
}
.pricing-card {
background: var(--surface);
border: 1px solid var(--border2);
border-radius: 20px;
padding: 2rem 1.75rem;
flex: 1; min-width: 220px; max-width: 290px;
text-align: center;
transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
position: relative;
}
.pricing-card:hover {
transform: translateY(-4px);
box-shadow: 0 24px 48px rgba(0,0,0,0.4);
border-color: var(--border2);
}
.pricing-card.featured {
border-color: var(--gold);
background: linear-gradient(160deg, #1A1A0A 0%, #1A1505 100%);
transform: translateY(-8px);
box-shadow: 0 32px 64px rgba(245,166,35,0.12), 0 0 0 1px var(--gold);
}
.pricing-badge {
position: absolute; top: -13px; left: 50%; transform: translateX(-50%);
background: var(--gold);
color: #080B0F;
font-size: 0.62rem; font-weight: 800;
padding: 4px 14px; border-radius: 99px;
text-transform: uppercase; letter-spacing: 0.1em;
white-space: nowrap;
font-family: var(--font-body);
}
.pricing-plan-name {
font-size: 0.7rem; font-weight: 700; letter-spacing: 0.15em;
text-transform: uppercase; color: var(--text-muted);
margin-bottom: 0.75rem;
font-family: var(--font-body);
}
.pricing-price {
font-size: 2.2rem; font-weight: 700; color: var(--text-primary);
font-family: var(--font-mono); line-height: 1;
letter-spacing: -0.03em;
}
.pricing-price span {
font-size: 0.9rem; font-weight: 400; color: var(--text-muted);
font-family: var(--font-body);
}
.pricing-desc {
font-size: 0.78rem; color: var(--text-muted);
margin: 0.5rem 0 1.25rem 0;
}
.pricing-features {
list-style: none; padding: 0; margin: 0 0 1.5rem 0; text-align: left;
}
.pricing-features li {
font-size: 0.82rem; color: var(--text-secondary);
padding: 0.4rem 0; border-bottom: 1px solid var(--border);
display: flex; align-items: center; gap: 0.5rem;
}
.pricing-features li:last-child { border-bottom: none; }
.pricing-features li::before {
content: "✓"; color: var(--jade);
font-weight: 700; flex-shrink: 0;
}

/* ── Forgot password ── */
.forgot-link {
font-size: 0.82rem; color: var(--gold);
text-decoration: none; cursor: pointer; font-weight: 500;
}

/* ── Form containers ── */
[data-testid="stForm"] {
background: transparent !important;
border: none !important;
}
.stForm { border: none !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
background: var(--surface) !important;
border: 1px solid var(--border) !important;
border-radius: 12px !important;
}
[data-testid="stExpander"] summary {
color: var(--text-secondary) !important;
font-family: var(--font-body) !important;
}

/* ── Info / Warning / Success / Error boxes ── */
[data-testid="stAlert"] {
border-radius: 12px !important;
border-left-width: 3px !important;
font-family: var(--font-body) !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] { color: var(--gold) !important; }

/* ── Plan radio button enhancement ── */
.stRadio > div > label {
background: var(--surface) !important;
border: 1px solid var(--border2) !important;
border-radius: 10px !important;
padding: 0.75rem 1rem !important;
transition: border-color 0.15s !important;
}
.stRadio > div > label:has(input:checked) {
border-color: var(--gold) !important;
background: var(--gold-glow) !important;
}

/* ── Login landing page ── */
.lp-hero { text-align:center; padding:2.5rem 1rem 1.5rem 1rem; }
.lp-logo-wrap {
display:inline-flex; align-items:center; gap:0.75rem;
margin-bottom:1.25rem;
}
.lp-logo-icon {
width:52px; height:52px; border-radius:14px;
background:linear-gradient(135deg,#F5A623,#C4831A);
display:flex; align-items:center; justify-content:center;
font-size:1.6rem; box-shadow:0 8px 28px rgba(245,166,35,0.45);
}
.lp-logo-text {
font-family:'Syne',sans-serif;
font-size:2.2rem; font-weight:800;
color:#F0F4F8; letter-spacing:-0.05em;
}
.lp-badge {
display:inline-flex; align-items:center; gap:0.45rem;
background:rgba(245,166,35,0.1); border:1px solid rgba(245,166,35,0.3);
border-radius:99px; padding:0.35rem 1rem;
font-size:0.75rem; color:#F5A623; font-weight:600;
letter-spacing:0.04em; margin-bottom:1.25rem;
}
.lp-headline {
font-family:'Syne',sans-serif;
font-size:clamp(1.7rem,5vw,2.6rem);
font-weight:800; color:#F0F4F8;
letter-spacing:-0.04em; line-height:1.15; margin-bottom:0.75rem;
}
.lp-headline span { color:#F5A623; }
.lp-sub {
font-size:1rem; color:#8BA0B8;
max-width:520px; margin:0 auto 1.75rem auto; line-height:1.65;
}
.lp-value-grid {
display:grid; grid-template-columns:repeat(4,1fr);
gap:0.75rem; max-width:720px; margin:0 auto 2rem auto;
}
.lp-value-card {
background:#111827; border:1px solid #1F2D3D;
border-radius:14px; padding:1.1rem 1rem;
text-align:center; transition:border-color 0.2s;
}
.lp-value-card:hover { border-color:#F5A623; }
.lp-value-icon { font-size:1.5rem; margin-bottom:0.4rem; }
.lp-value-title {
font-family:'Syne',sans-serif; font-size:0.8rem; font-weight:700;
color:#F0F4F8; margin-bottom:0.2rem;
}
.lp-value-desc { font-size:0.72rem; color:#4A6080; line-height:1.4; }
.lp-divider {
display:flex; align-items:center; gap:1rem;
max-width:480px; margin:0 auto 1.5rem auto;
}
.lp-divider::before, .lp-divider::after {
content:''; flex:1; border-top:1px solid #1F2D3D;
}
.lp-divider span { font-size:0.75rem; color:#4A6080; white-space:nowrap; }
.lp-trust-strip {
display:flex; justify-content:center; align-items:center;
gap:1.5rem; flex-wrap:wrap; padding:1rem 0;
border-top:1px solid #1F2D3D; margin-top:1rem;
}
.lp-trust-item { display:flex; align-items:center; gap:0.4rem; font-size:0.75rem; color:#4A6080; }
.lp-trust-item span { color:#00C896; }
@media (max-width:600px) {
.lp-value-grid { grid-template-columns:1fr 1fr !important; }
.lp-trust-strip { gap:0.75rem; }
}

</style>
    """, unsafe_allow_html=True)


def inject_sidebar_toggle():
    """
    Forces Streamlit's native sidebar toggle to remain visible and functional.
    We do NOT inject a competing custom button — the native toggle is already
    restored via CSS. This function is kept for backward compatibility.
    """
    st.markdown("""
<script>
(function() {
// Ensure Streamlit's own sidebar toggle button stays visible.
// We find it by every known selector and force visibility.
function ensureToggleVisible() {
var selectors = [
'[data-testid="collapsedControl"]',
'[data-testid="stSidebarCollapsedControl"]',
'[data-testid="stSidebarToggle"]',
'[data-testid="stSidebarToggleButton"]',
'button[aria-label="Open sidebar"]',
'button[aria-label="Close sidebar"]',
'button[aria-label="collapse sidebar"]',
'button[aria-label="expand sidebar"]'
];
selectors.forEach(function(sel) {
var el = document.querySelector(sel);
if (el) {
el.style.display    = '';
el.style.visibility = 'visible';
el.style.opacity    = '1';
el.style.pointerEvents = 'auto';
}
});
}
// Run immediately and after a short delay to catch late mounts
ensureToggleVisible();
setTimeout(ensureToggleVisible, 500);
setTimeout(ensureToggleVisible, 1500);
})();
</script>
    """, unsafe_allow_html=True)


def inject_sidebar_toggle():
    """
    Forces Streamlit's native sidebar toggle to remain visible and functional.
    We do NOT inject a competing custom button — the native toggle is already
    restored via CSS. This function is kept for backward compatibility.
    """
    st.markdown("""
<script>
(function() {
// Ensure Streamlit's own sidebar toggle button stays visible.
// We find it by every known selector and force visibility.
function ensureToggleVisible() {
var selectors = [
'[data-testid="collapsedControl"]',
'[data-testid="stSidebarCollapsedControl"]',
'[data-testid="stSidebarToggle"]',
'[data-testid="stSidebarToggleButton"]',
'button[aria-label="Open sidebar"]',
'button[aria-label="Close sidebar"]',
'button[aria-label="collapse sidebar"]',
'button[aria-label="expand sidebar"]'
];
selectors.forEach(function(sel) {
var el = document.querySelector(sel);
if (el) {
el.style.display    = '';
el.style.visibility = 'visible';
el.style.opacity    = '1';
el.style.pointerEvents = 'auto';
}
});
}
// Run immediately and after a short delay to catch late mounts
ensureToggleVisible();
setTimeout(ensureToggleVisible, 500);
setTimeout(ensureToggleVisible, 1500);
})();
</script>
    """, unsafe_allow_html=True)
