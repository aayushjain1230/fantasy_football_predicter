from __future__ import annotations

import streamlit as st


GLOBAL_CSS = """
:root {
  --fd-bg: #080b10;
  --fd-panel: #0f141c;
  --fd-panel-2: #141a23;
  --fd-line: #252d38;
  --fd-line-soft: #1b222c;
  --fd-text: #f4f6f8;
  --fd-soft: #bdc5d0;
  --fd-muted: #7e8998;
  --fd-faint: #566171;
  --fd-orange: #ff6a13;
  --fd-orange-2: #ff8a2a;
  --fd-orange-soft: rgba(255,106,19,.12);
  --fd-green: #49d17d;
  --fd-green-soft: rgba(73,209,125,.11);
  --fd-blue: #63a6ff;
  --fd-blue-soft: rgba(99,166,255,.11);
  --fd-gold: #f4c95d;
  --fd-gold-soft: rgba(244,201,93,.11);
  --fd-red: #ff6b6b;
  --fd-red-soft: rgba(255,107,107,.11);
  --fd-purple: #a98bff;
  --fd-purple-soft: rgba(169,139,255,.11);
  --fd-radius: 12px;
  --fd-radius-lg: 16px;
  --fd-shadow: 0 14px 40px rgba(0,0,0,.22);
  --fd-body: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --fd-display: "Arial Narrow", "Roboto Condensed", Inter, sans-serif;
  --fd-mono: "SFMono-Regular", Consolas, monospace;
}

html, body, [class*="css"] { font-family: var(--fd-body); }
html, body { color: var(--fd-text); background: var(--fd-bg); overflow-x: hidden; }
[data-testid="stAppViewContainer"] {
  min-height: 100vh;
  color: var(--fd-text);
  background:
    radial-gradient(900px 380px at 62% -180px, rgba(255,106,19,.09), transparent 72%),
    linear-gradient(180deg, #0a0e14 0%, var(--fd-bg) 48%);
  overflow-x: hidden;
}
[data-testid="stMain"], [data-testid="stMainBlockContainer"] { min-width: 0 !important; overflow-x: hidden; }
.block-container {
  width: 100% !important;
  max-width: 1180px !important;
  min-width: 0 !important;
  padding: 1.6rem 2rem 4rem !important;
  margin-inline: auto;
}
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

h1,h2,h3,h4,h5,h6 { color: var(--fd-text); letter-spacing: -.025em; }
h1 { font-size: clamp(2rem, 4vw, 3.15rem); line-height: 1.02; }
h2 { font-size: clamp(1.35rem, 2.2vw, 1.9rem); }
h3 { font-size: 1rem; }
p,li,label,[data-testid="stMarkdownContainer"] { color: var(--fd-soft); }
a { color: var(--fd-text); text-underline-offset: 3px; }
a:hover { color: var(--fd-orange-2); }
code,pre { font-family: var(--fd-mono); }

section[data-testid="stSidebar"] {
  width: 260px !important;
  background: #0b0f15;
  border-right: 1px solid var(--fd-line-soft);
  box-shadow: none;
}
section[data-testid="stSidebar"] > div { padding-top: .85rem; }
.fd-brand { display:flex; align-items:center; gap:11px; padding:7px 8px 17px; }
.fd-brand-mark {
  width:38px; height:38px; display:grid; place-items:center;
  color:#fff; border:1px solid rgba(255,255,255,.12); border-radius:10px;
  background:var(--fd-orange); box-shadow:0 8px 20px rgba(255,106,19,.19);
  font-family:var(--fd-display); font-size:16px; font-weight:900;
}
.fd-brand-name { color:var(--fd-text); font-size:.96rem; font-weight:800; }
.fd-brand-subtitle { color:var(--fd-faint); margin-top:2px; font-size:.68rem; }
.fd-sidebar-context {
  margin:0 8px 10px; padding:13px; border:1px solid var(--fd-line-soft);
  border-radius:12px; background:#0f141c;
}
.fd-sidebar-team { color:var(--fd-text); font-size:.86rem; font-weight:700; margin-bottom:8px; }
.fd-nav-label { color:var(--fd-faint); padding:12px 11px 6px; font-size:.61rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; }
section[data-testid="stSidebar"] [role="radiogroup"] { gap:2px; }
section[data-testid="stSidebar"] [data-baseweb="radio"] {
  min-height:38px; padding:6px 9px; border:1px solid transparent; border-radius:9px;
  transition:background 120ms ease,border-color 120ms ease,transform 120ms ease;
}
section[data-testid="stSidebar"] [data-baseweb="radio"]:hover { background:#121821; }
section[data-testid="stSidebar"] [data-baseweb="radio"]:active { transform:scale(.985); }
section[data-testid="stSidebar"] [aria-checked="true"] {
  background:var(--fd-orange-soft); border-color:rgba(255,106,19,.22);
}
section[data-testid="stSidebar"] .stRadio label { color:var(--fd-soft); font-size:.87rem; }

.fd-stadium-hero {
  position:relative; isolation:isolate; overflow:hidden;
  min-height:430px; padding:48px 46px 34px; margin-bottom:18px;
  border:1px solid #242b35; border-radius:16px;
  background:
    linear-gradient(90deg, rgba(5,7,10,.94) 0%, rgba(7,10,14,.66) 58%, rgba(5,7,10,.92) 100%),
    radial-gradient(ellipse at 50% 118%, rgba(30,104,57,.42), transparent 52%),
    linear-gradient(180deg, #161d28, #080b10 74%);
  box-shadow:var(--fd-shadow);
}
.fd-stadium-hero::before,.fd-stadium-hero::after {
  content:""; position:absolute; top:-26px; z-index:-1; width:170px; height:96px; opacity:.86;
  background:
    repeating-linear-gradient(90deg, #fff 0 4px, transparent 4px 10px),
    repeating-linear-gradient(0deg, rgba(255,255,255,.62) 0 4px, transparent 4px 10px);
  filter:drop-shadow(0 0 18px rgba(215,235,255,.56));
  mask-image:radial-gradient(ellipse, black 34%, transparent 73%);
}
.fd-stadium-hero::before { left:-27px; transform:rotate(8deg); }
.fd-stadium-hero::after { right:-27px; transform:rotate(-8deg); }
.fd-stadium-vignette {
  position:absolute; inset:0; z-index:-2; pointer-events:none;
  background:
    repeating-linear-gradient(90deg, transparent 0 9.7%, rgba(255,255,255,.022) 9.8% 10%),
    linear-gradient(180deg, transparent 68%, rgba(6,27,15,.46));
}
.fd-hero-content { width:min(820px,100%); margin:0 auto; text-align:center; min-width:0; }
.fd-hero-kicker {
  display:inline-flex; color:var(--fd-orange-2); padding:6px 10px; margin-bottom:18px;
  border:1px solid rgba(255,106,19,.25); border-radius:999px; background:rgba(255,106,19,.07);
  font-size:.61rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase;
}
.fd-hero-title {
  max-width:780px; margin:0 auto; color:#fff; font-family:var(--fd-display);
  font-size:clamp(2.35rem,5.2vw,4.5rem) !important; font-weight:900; line-height:.96 !important;
  letter-spacing:-.035em; text-transform:uppercase; overflow-wrap:anywhere;
  text-shadow:0 9px 30px rgba(0,0,0,.62);
}
.fd-hero-title-accent { display:block; color:#eef2f6; }
.fd-hero-description { max-width:620px; margin:17px auto 0; color:var(--fd-muted); font-size:.91rem; line-height:1.6; }
.fd-feature-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:9px; margin-top:28px; }
.fd-feature-tile {
  min-width:0; min-height:82px; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:7px; padding:13px 8px; border:1px solid rgba(255,255,255,.05); border-radius:10px;
  background:rgba(7,10,14,.54);
}
.fd-feature-icon { color:var(--fd-orange); font-family:var(--fd-mono); font-size:1rem; font-weight:800; }
.fd-feature-label {
  color:#aeb7c3; font-family:var(--fd-display); font-size:.68rem; font-weight:800;
  letter-spacing:.06em; text-align:center; text-transform:uppercase;
}

.fd-page-header { display:flex; justify-content:space-between; align-items:flex-end; gap:22px; margin:6px 0 22px; }
.fd-page-eyebrow { color:var(--fd-orange); margin-bottom:7px; font-size:.62rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; }
.fd-page-title { margin:0; color:var(--fd-text); font-size:clamp(1.9rem,3.3vw,2.8rem); font-weight:800; line-height:1.04; }
.fd-page-subtitle { max-width:690px; margin-top:8px; color:var(--fd-muted); font-size:.86rem; line-height:1.5; }
.fd-page-meta { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:7px; }
.fd-section-header { display:flex; justify-content:space-between; align-items:flex-end; gap:18px; margin:27px 0 12px; }
.fd-section-title { color:var(--fd-text); font-size:1rem; font-weight:750; }
.fd-section-description { margin-top:4px; color:var(--fd-muted); font-size:.74rem; }

.fd-card, div[data-testid="stVerticalBlockBorderWrapper"] {
  border:1px solid var(--fd-line-soft); border-radius:var(--fd-radius-lg);
  background:var(--fd-panel); box-shadow:none;
}
.fd-card { padding:19px; }
.fd-card-label,.fd-metric-label { color:var(--fd-muted); font-size:.69rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
.fd-card-title { margin-top:5px; color:var(--fd-text); font-size:.96rem; font-weight:700; }
.fd-card-copy { margin-top:7px; color:var(--fd-muted); font-size:.8rem; line-height:1.5; }
.fd-matchup-line { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-top:12px; color:var(--fd-text); font-size:1.05rem; }
.fd-matchup-line span { color:var(--fd-orange); font-family:var(--fd-display); }

.fd-metric-card {
  position:relative; overflow:hidden; min-height:125px; padding:18px;
  border:1px solid var(--fd-line-soft); border-top:2px solid var(--fd-orange);
  border-radius:12px; background:var(--fd-panel);
}
.fd-metric-value { margin-top:13px; color:var(--fd-text); font-family:var(--fd-mono); font-size:clamp(1.45rem,2.6vw,2.15rem); font-weight:760; line-height:1; }
.fd-metric-footer { display:flex; justify-content:space-between; gap:8px; margin-top:12px; color:var(--fd-muted); font-size:.68rem; }
.fd-metric-delta { font-weight:700; }
.fd-delta-positive { color:var(--fd-green); }
.fd-delta-negative { color:var(--fd-red); }
.fd-delta-neutral { color:var(--fd-muted); }

.fd-action-card {
  padding:16px 18px; margin-bottom:9px; border:1px solid var(--fd-line-soft);
  border-left:3px solid var(--fd-action-color,var(--fd-orange)); border-radius:10px;
  background:var(--fd-panel);
}
.fd-action-priority { color:var(--fd-action-color,var(--fd-orange)); font-size:.59rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; }
.fd-action-title { margin-top:5px; color:var(--fd-text); font-size:.94rem; font-weight:720; }
.fd-action-copy { margin-top:5px; color:var(--fd-muted); font-size:.77rem; line-height:1.45; }
.fd-action-impact { margin-top:9px; color:var(--fd-soft); font-family:var(--fd-mono); font-size:.69rem; }

.fd-player-card {
  display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:13px;
  padding:14px; margin-bottom:8px; border:1px solid var(--fd-line-soft); border-radius:10px; background:var(--fd-panel);
}
.fd-player-avatar { width:43px; height:43px; display:grid; place-items:center; color:var(--fd-orange-2); border:1px solid #303846; border-radius:9px; background:#171d26; font-family:var(--fd-display); font-weight:850; }
.fd-player-name { color:var(--fd-text); font-size:.9rem; font-weight:720; }
.fd-player-meta { margin-top:3px; color:var(--fd-muted); font-size:.68rem; }
.fd-player-numbers { display:flex; align-items:center; gap:16px; }
.fd-player-stat { min-width:55px; text-align:right; }
.fd-player-stat-label { color:var(--fd-faint); font-size:.56rem; letter-spacing:.07em; text-transform:uppercase; }
.fd-player-stat-value { margin-top:3px; color:var(--fd-text); font-family:var(--fd-mono); font-size:.79rem; font-weight:700; }

.fd-badge { display:inline-flex; align-items:center; width:fit-content; padding:4px 8px; border:1px solid transparent; border-radius:999px; font-size:.57rem; font-weight:800; letter-spacing:.07em; line-height:1.1; text-transform:uppercase; white-space:nowrap; }
.fd-badge-start,.fd-badge-live,.fd-badge-positive { color:var(--fd-green); border-color:rgba(73,209,125,.2); background:var(--fd-green-soft); }
.fd-badge-hold,.fd-badge-info { color:var(--fd-blue); border-color:rgba(99,166,255,.2); background:var(--fd-blue-soft); }
.fd-badge-watch,.fd-badge-cached { color:var(--fd-gold); border-color:rgba(244,201,93,.2); background:var(--fd-gold-soft); }
.fd-badge-trade { color:var(--fd-orange-2); border-color:rgba(255,106,19,.2); background:var(--fd-orange-soft); }
.fd-badge-drop,.fd-badge-danger,.fd-badge-unavailable { color:var(--fd-red); border-color:rgba(255,107,107,.2); background:var(--fd-red-soft); }
.fd-badge-simulation,.fd-badge-model { color:var(--fd-purple); border-color:rgba(169,139,255,.2); background:var(--fd-purple-soft); }

.stButton > button,.stDownloadButton > button,.stFormSubmitButton > button {
  min-height:40px; padding:0 16px; color:var(--fd-text); border:1px solid #313a47; border-radius:9px;
  background:#171d26; box-shadow:none; font-weight:700;
  transition:background 120ms ease,border-color 120ms ease,transform 80ms ease;
}
.stButton > button:hover,.stDownloadButton > button:hover,.stFormSubmitButton > button:hover { color:#fff; border-color:#485363; background:#1c2430; }
.stButton > button:active,.stDownloadButton > button:active,.stFormSubmitButton > button:active { transform:translateY(1px) scale(.99); }
.stButton > button[kind="primary"],.stFormSubmitButton > button[kind="primary"] {
  color:#fff; border-color:var(--fd-orange); background:var(--fd-orange); box-shadow:0 7px 18px rgba(255,106,19,.17);
}
.stButton > button[kind="primary"]:hover,.stFormSubmitButton > button[kind="primary"]:hover { background:var(--fd-orange-2); }

[data-baseweb="input"] > div,[data-baseweb="select"] > div,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input {
  color:var(--fd-text); border-color:#303846 !important; border-radius:9px !important; background:#0d1218 !important; box-shadow:none !important;
}
[data-baseweb="input"] > div:focus-within,[data-baseweb="select"] > div:focus-within,[data-testid="stTextArea"] textarea:focus,[data-testid="stNumberInput"] input:focus {
  border-color:var(--fd-orange) !important; box-shadow:0 0 0 2px rgba(255,106,19,.12) !important;
}
input::placeholder,textarea::placeholder { color:var(--fd-faint) !important; }
[data-baseweb="tab-list"] { gap:3px; padding:3px; border:1px solid var(--fd-line-soft); border-radius:10px; background:#0d1218; overflow-x:auto; }
[data-baseweb="tab"] { min-height:36px; padding:0 12px; color:var(--fd-muted); border-radius:7px; font-size:.75rem; font-weight:650; white-space:nowrap; }
[data-baseweb="tab"][aria-selected="true"] { color:#fff; background:#1a212b; }
[data-baseweb="tab-highlight"] { display:none; }
[data-testid="stExpander"] { overflow:hidden; border:1px solid var(--fd-line-soft) !important; border-radius:10px !important; background:var(--fd-panel); }
[data-testid="stMetric"] { padding:15px; border:1px solid var(--fd-line-soft); border-radius:10px; background:var(--fd-panel); }
[data-testid="stMetricLabel"] { color:var(--fd-muted); }
[data-testid="stMetricValue"] { color:var(--fd-text); font-family:var(--fd-mono); letter-spacing:-.035em; }
[data-testid="stDataFrame"] { max-width:100%; overflow:hidden; border:1px solid var(--fd-line-soft); border-radius:10px; background:var(--fd-panel); }

.fd-state { padding:16px; border:1px solid var(--fd-line-soft); border-radius:10px; background:var(--fd-panel); }
.fd-state-title { color:var(--fd-text); font-size:.88rem; font-weight:720; }
.fd-state-copy { margin-top:5px; color:var(--fd-muted); font-size:.76rem; line-height:1.5; }
.fd-state-warning { border-color:rgba(244,201,93,.2); background:linear-gradient(90deg,var(--fd-gold-soft),var(--fd-panel) 46%); }

* { scrollbar-width:thin; scrollbar-color:#303846 transparent; }
*::-webkit-scrollbar { width:8px; height:8px; }
*::-webkit-scrollbar-thumb { border:2px solid transparent; border-radius:999px; background:#303846; background-clip:padding-box; }

@media (max-width: 1100px) {
  .block-container { padding-inline:1.35rem !important; }
  .fd-feature-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width: 760px) {
  .block-container { padding:1rem .85rem 3rem !important; }
  .fd-page-header { display:block; }
  .fd-page-meta { justify-content:flex-start; margin-top:12px; }
  .fd-stadium-hero { min-height:0; padding:38px 17px 23px; border-radius:12px; }
  .fd-hero-title { font-size:clamp(1.8rem,9vw,2.3rem) !important; line-height:1.02 !important; }
  .fd-hero-description { font-size:.84rem; }
  .fd-feature-grid { grid-template-columns:repeat(2,minmax(0,1fr)); margin-top:22px; }
  .fd-feature-tile { min-height:72px; }
  .fd-player-card { grid-template-columns:auto minmax(0,1fr); }
  .fd-player-numbers { grid-column:1/-1; justify-content:space-between; padding-top:10px; border-top:1px solid var(--fd-line-soft); }
  .fd-player-stat { text-align:left; }
}
@media (prefers-reduced-motion: reduce) {
  *,*::before,*::after { animation-duration:.01ms !important; transition-duration:.01ms !important; }
}

.fd-league-card {
  margin:14px 0; padding:20px; border:1px solid rgba(255,106,19,.28);
  border-radius:14px; background:linear-gradient(145deg,#171c23,#10141a);
  box-shadow:0 14px 32px rgba(0,0,0,.2);
}
.fd-league-name { color:var(--fd-text); font-size:1.08rem; font-weight:780; }
.fd-league-meta,.fd-league-team,.fd-league-status { margin-top:7px; color:var(--fd-muted); font-size:.82rem; line-height:1.4; }
.fd-league-team { color:var(--fd-text); font-weight:650; }
.fd-league-status { color:var(--fd-gold); }

/* 2026 product refresh: restrained, editorial, and decision-first. */
:root {
  --fd-bg:#0b0e12;
  --fd-panel:#12161c;
  --fd-panel-2:#171c23;
  --fd-line:#29313b;
  --fd-line-soft:#202731;
  --fd-text:#f7f7f5;
  --fd-soft:#c4c9d0;
  --fd-muted:#8f98a5;
  --fd-faint:#697381;
  --fd-orange:#f26a21;
  --fd-orange-2:#ff7b32;
  --fd-radius:8px;
  --fd-radius-lg:10px;
  --fd-shadow:0 10px 30px rgba(0,0,0,.18);
  --fd-display:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
[data-testid="stAppViewContainer"] { background:var(--fd-bg); }
.block-container { max-width:1080px !important; padding-top:2.2rem !important; }
section[data-testid="stSidebar"] { background:#0e1217; width:248px !important; }
.fd-brand-mark { border-radius:8px; box-shadow:none; font-size:14px; letter-spacing:-.03em; }
.fd-brand-name { font-size:1rem; letter-spacing:-.01em; }
.fd-sidebar-context { background:transparent; border-color:var(--fd-line-soft); border-radius:8px; }
.fd-nav-label { font-size:.68rem; letter-spacing:.08em; text-transform:none; }
section[data-testid="stSidebar"] [data-baseweb="radio"] { border-radius:7px; }
section[data-testid="stSidebar"] [aria-checked="true"] { background:#1b2028; border-color:#343d49; }
.fd-page-header { align-items:flex-start; padding-bottom:18px; border-bottom:1px solid var(--fd-line-soft); margin-bottom:22px; }
.fd-page-eyebrow { color:var(--fd-muted); font-size:.72rem; letter-spacing:.04em; text-transform:none; }
.fd-page-title { font-size:clamp(2rem,3vw,2.65rem); font-weight:720; letter-spacing:-.045em; }
.fd-page-subtitle { font-size:.92rem; color:var(--fd-muted); }
.fd-section-header { margin-top:30px; }
.fd-section-title { font-size:1.08rem; font-weight:700; }
.fd-section-description { font-size:.8rem; }
.fd-card,.fd-metric-card,.fd-action-card,.fd-player-card,div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:9px; background:var(--fd-panel); }
.fd-metric-card { min-height:112px; border-top:1px solid var(--fd-line-soft); padding:17px; }
.fd-metric-label,.fd-card-label { text-transform:none; letter-spacing:0; font-size:.76rem; }
.fd-metric-value { font-family:var(--fd-body); font-size:1.8rem; font-weight:700; letter-spacing:-.035em; }
.fd-action-card { border-left-width:2px; padding:17px; }
.fd-action-priority { font-size:.68rem; letter-spacing:.04em; text-transform:none; }
.fd-action-title { font-size:1rem; }
.fd-action-impact { font-family:var(--fd-body); }
.fd-player-avatar { border-radius:50%; background:#1b2129; }
.fd-player-stat-value,[data-testid="stMetricValue"] { font-family:var(--fd-body); }
.fd-badge { border-radius:6px; letter-spacing:.02em; text-transform:none; font-size:.64rem; }
[data-baseweb="tab-list"] { padding:0; gap:18px; border:0; border-bottom:1px solid var(--fd-line-soft); border-radius:0; background:transparent; }
[data-baseweb="tab"] { padding:0 2px; border-radius:0; font-size:.82rem; }
[data-baseweb="tab"][aria-selected="true"] { color:#fff; background:transparent; border-bottom:2px solid var(--fd-orange); }
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button { border-radius:7px; background:#181e26; font-weight:650; }
[data-testid="stExpander"],[data-testid="stMetric"],[data-testid="stDataFrame"] { border-radius:8px !important; }
.fd-stadium-hero { min-height:360px; padding:52px 44px 34px; background:#11161d; border-color:var(--fd-line); box-shadow:none; }
.fd-stadium-hero::before,.fd-stadium-hero::after,.fd-stadium-vignette { display:none; }
.fd-hero-kicker { color:var(--fd-muted); border:0; background:transparent; letter-spacing:.04em; text-transform:none; }
.fd-hero-title { max-width:700px; font-family:var(--fd-body); font-size:clamp(2.3rem,5vw,4rem) !important; font-weight:730; line-height:1.02 !important; letter-spacing:-.055em; text-transform:none; text-shadow:none; }
.fd-hero-title-accent { color:var(--fd-orange-2); }
.fd-feature-tile { background:#151b22; border-color:var(--fd-line-soft); border-radius:8px; }
.fd-feature-label { font-family:var(--fd-body); font-size:.72rem; letter-spacing:0; text-transform:none; }
.fd-feature-icon { font-family:var(--fd-body); font-size:.78rem; }
"""


def inject_global_styles() -> None:
    st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)
