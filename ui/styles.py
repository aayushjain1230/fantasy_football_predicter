from __future__ import annotations

import streamlit as st


GLOBAL_CSS = """
:root {
  --fd-bg: #080A0F;
  --fd-bg-elevated: #0D1118;
  --fd-surface: #11151D;
  --fd-surface-2: #171C25;
  --fd-surface-3: #1C222D;
  --fd-border: rgba(255, 255, 255, 0.08);
  --fd-border-strong: rgba(255, 255, 255, 0.14);
  --fd-text: #F8FAFC;
  --fd-text-soft: #CBD5E1;
  --fd-text-muted: #8B95A7;
  --fd-text-faint: #5E6878;
  --fd-green: #4ADE80;
  --fd-green-soft: rgba(74, 222, 128, 0.12);
  --fd-blue: #3B82F6;
  --fd-blue-soft: rgba(59, 130, 246, 0.12);
  --fd-gold: #FBBF24;
  --fd-gold-soft: rgba(251, 191, 36, 0.12);
  --fd-orange: #F97316;
  --fd-orange-soft: rgba(249, 115, 22, 0.12);
  --fd-red: #EF4444;
  --fd-red-soft: rgba(239, 68, 68, 0.12);
  --fd-purple: #8B5CF6;
  --fd-purple-soft: rgba(139, 92, 246, 0.12);
  --fd-radius-sm: 10px;
  --fd-radius-md: 16px;
  --fd-radius-lg: 20px;
  --fd-radius-xl: 24px;
  --fd-radius-pill: 999px;
  --fd-shadow-sm: 0 1px 2px rgba(0,0,0,0.20), 0 8px 24px rgba(0,0,0,0.13);
  --fd-shadow-md: 0 2px 4px rgba(0,0,0,0.24), 0 18px 54px rgba(0,0,0,0.27);
  --fd-font-body: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --fd-font-display: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --fd-font-sport: "Arial Narrow", "Roboto Condensed", Impact, sans-serif;
  --fd-font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  --fd-transition: 180ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

html, body, [class*="css"] { font-family: var(--fd-font-body); }
html, body { color: var(--fd-text); background: var(--fd-bg); }
[data-testid="stAppViewContainer"] {
  min-height: 100vh;
  color: var(--fd-text);
  background:
    radial-gradient(circle at 50% -12%, rgba(59,130,246,0.075), transparent 33%),
    radial-gradient(circle at 93% 8%, rgba(249,115,22,0.045), transparent 25%),
    linear-gradient(180deg, #0A0D13 0%, #080A0F 42%, #07090D 100%);
}
[data-testid="stAppViewContainer"]::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.13;
  background-image:
    linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(to bottom, black, transparent 78%);
}
[data-testid="stMain"] { position: relative; z-index: 1; }
.block-container { max-width: 1480px; padding: 2rem 2.4rem 4rem; animation: fd-page-enter 280ms ease both; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

h1,h2,h3,h4,h5,h6 { color: var(--fd-text); font-family: var(--fd-font-display); letter-spacing: -0.025em; }
h1 { font-size: clamp(2.1rem, 4vw, 3.8rem); font-weight: 780; line-height: 1.02; }
h2 { font-size: clamp(1.45rem, 2vw, 2.1rem); font-weight: 730; line-height: 1.12; }
h3 { font-size: 1.08rem; font-weight: 690; }
p,li,label,[data-testid="stMarkdownContainer"] { color: var(--fd-text-soft); }
a { color: var(--fd-text); text-decoration-color: rgba(255,255,255,0.24); text-underline-offset: 3px; }
a:hover { color: var(--fd-green); text-decoration-color: var(--fd-green); }
code,pre { font-family: var(--fd-font-mono); }

section[data-testid="stSidebar"] {
  width: 278px !important;
  background: linear-gradient(180deg, rgba(17,21,29,0.98), rgba(8,10,15,0.995));
  border-right: 1px solid var(--fd-border);
  box-shadow: 18px 0 60px rgba(0,0,0,0.22);
}
section[data-testid="stSidebar"] > div { padding-top: 1rem; }
.fd-brand { display: flex; align-items: center; gap: 12px; padding: 6px 8px 20px; }
.fd-brand-mark {
  width: 40px; height: 40px; display: grid; place-items: center;
  border: 1px solid rgba(255,255,255,0.11); border-radius: 12px; color: #fff;
  background: linear-gradient(145deg, var(--fd-gold), var(--fd-orange));
  box-shadow: 0 8px 28px rgba(249,115,22,0.24), inset 0 1px rgba(255,255,255,0.16);
  font-family: var(--fd-font-sport); font-size: 18px; font-weight: 900;
}
.fd-brand-name { color: var(--fd-text); font-size: 1rem; font-weight: 780; letter-spacing: -0.025em; }
.fd-brand-subtitle { color: var(--fd-text-faint); margin-top: 2px; font-size: 0.7rem; }
.fd-sidebar-context { margin: 0 8px 12px; padding: 14px; border: 1px solid var(--fd-border); border-radius: 16px; background: rgba(255,255,255,0.025); }
.fd-sidebar-team { color: var(--fd-text); font-weight: 700; margin-bottom: 8px; }
.fd-nav-label { color: var(--fd-text-faint); padding: 12px 12px 7px; font-size: 0.65rem; font-weight: 760; letter-spacing: 0.13em; text-transform: uppercase; }
section[data-testid="stSidebar"] .stRadio label { color: var(--fd-text-soft); }
section[data-testid="stSidebar"] [role="radiogroup"] { gap: 4px; }
section[data-testid="stSidebar"] [data-baseweb="radio"] {
  min-height: 42px; padding: 7px 10px; border-radius: 12px; border: 1px solid transparent;
  transition: color var(--fd-transition), background var(--fd-transition), border-color var(--fd-transition), transform var(--fd-transition);
}
section[data-testid="stSidebar"] [data-baseweb="radio"]:hover { background: rgba(255,255,255,0.045); border-color: rgba(255,255,255,0.06); transform: translateX(2px); }
section[data-testid="stSidebar"] [aria-checked="true"] { background: linear-gradient(90deg, rgba(249,115,22,0.13), rgba(249,115,22,0.025)); border-color: rgba(249,115,22,0.13); }

.fd-stadium-hero {
  position: relative; isolation: isolate; overflow: hidden; min-height: 510px;
  display: flex; align-items: center; justify-content: center;
  padding: 66px 34px 54px; margin-bottom: 30px;
  border: 1px solid var(--fd-border); border-radius: var(--fd-radius-xl);
  background:
    radial-gradient(ellipse at 50% 128%, rgba(25,87,53,0.25), transparent 48%),
    radial-gradient(circle at 9% 3%, rgba(219,234,254,0.15), transparent 19%),
    radial-gradient(circle at 91% 3%, rgba(219,234,254,0.15), transparent 19%),
    linear-gradient(180deg, rgba(13,17,24,0.79), rgba(8,10,15,0.98));
  box-shadow: var(--fd-shadow-md);
}
.fd-stadium-hero::before,.fd-stadium-hero::after {
  content: ""; position: absolute; top: -18px; z-index: -1; width: 195px; height: 108px; opacity: 0.67;
  background:
    repeating-linear-gradient(90deg, rgba(255,255,255,0.92) 0 5px, transparent 5px 11px),
    repeating-linear-gradient(0deg, rgba(255,255,255,0.42) 0 5px, transparent 5px 11px);
  box-shadow: 0 0 30px rgba(219,234,254,0.48), 0 0 95px rgba(147,197,253,0.19);
  mask-image: radial-gradient(ellipse, black 38%, transparent 74%);
}
.fd-stadium-hero::before { left: -30px; transform: rotate(9deg); }
.fd-stadium-hero::after { right: -30px; transform: rotate(-9deg); }
.fd-stadium-vignette { position: absolute; inset: 0; z-index: -2; pointer-events: none; background: linear-gradient(90deg, rgba(0,0,0,0.46), transparent 21% 79%, rgba(0,0,0,0.46)), linear-gradient(180deg, transparent 38%, rgba(0,0,0,0.58)); }
.fd-hero-content { width: min(900px, 100%); text-align: center; }
.fd-hero-kicker { display: inline-flex; align-items: center; gap: 8px; color: var(--fd-gold); padding: 7px 12px; margin-bottom: 22px; border: 1px solid rgba(251,191,36,0.18); border-radius: var(--fd-radius-pill); background: rgba(251,191,36,0.07); font-size: 0.67rem; font-weight: 780; letter-spacing: 0.13em; text-transform: uppercase; }
.fd-hero-title { max-width: 940px; margin: 0 auto; color: #fff; font-family: var(--fd-font-sport); font-size: clamp(3rem, 7vw, 6.7rem); font-weight: 900; line-height: 0.93; letter-spacing: -0.035em; text-transform: uppercase; text-shadow: 0 2px 0 rgba(255,255,255,0.07), 0 12px 38px rgba(0,0,0,0.62); }
.fd-hero-title-accent { display: block; color: transparent; background: linear-gradient(100deg, #fff 8%, #DDE6F2 50%, #fff 90%); -webkit-background-clip: text; background-clip: text; }
.fd-hero-description { max-width: 670px; margin: 21px auto 0; color: var(--fd-text-muted); font-size: 0.98rem; line-height: 1.65; }
.fd-hero-actions { display: flex; justify-content: center; gap: 12px; margin-top: 30px; }
.fd-feature-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 38px; }
.fd-feature-tile { min-height: 126px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 11px; padding: 18px; color: var(--fd-text-muted); border: 1px solid transparent; border-radius: var(--fd-radius-md); background: rgba(255,255,255,0.012); transition: transform var(--fd-transition), background var(--fd-transition), border-color var(--fd-transition), color var(--fd-transition); }
.fd-feature-tile:hover { color: var(--fd-text); transform: translateY(-3px); background: rgba(255,255,255,0.032); border-color: var(--fd-border); }
.fd-feature-icon { color: var(--fd-orange); font-size: 1.75rem; filter: drop-shadow(0 0 12px rgba(249,115,22,0.2)); }
.fd-feature-label { color: currentColor; font-family: var(--fd-font-sport); font-size: 0.8rem; font-weight: 820; letter-spacing: 0.055em; text-align: center; text-transform: uppercase; }

.fd-page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 28px; }
.fd-page-eyebrow { color: var(--fd-orange); margin-bottom: 8px; font-size: 0.69rem; font-weight: 790; letter-spacing: 0.13em; text-transform: uppercase; }
.fd-page-title { margin: 0; color: var(--fd-text); font-size: clamp(2rem, 3vw, 3.15rem); font-weight: 790; line-height: 1.02; letter-spacing: -0.045em; }
.fd-page-subtitle { max-width: 720px; margin-top: 10px; color: var(--fd-text-muted); font-size: 0.92rem; line-height: 1.55; }
.fd-page-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }

.fd-card, div[data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid var(--fd-border); border-radius: var(--fd-radius-lg); background: linear-gradient(145deg, rgba(23,28,37,0.88), rgba(17,21,29,0.93)); box-shadow: var(--fd-shadow-sm); }
.fd-card { position: relative; overflow: hidden; padding: 24px; transition: transform var(--fd-transition), border-color var(--fd-transition), box-shadow var(--fd-transition); }
.fd-card:hover { transform: translateY(-3px); border-color: var(--fd-border-strong); box-shadow: var(--fd-shadow-md); }
.fd-card-static:hover { transform: none; box-shadow: var(--fd-shadow-sm); }
.fd-card-label { color: var(--fd-text-muted); font-size: 0.74rem; font-weight: 660; letter-spacing: 0.045em; text-transform: uppercase; }
.fd-card-title { margin-top: 5px; color: var(--fd-text); font-size: 1rem; font-weight: 710; }
.fd-card-copy { margin-top: 8px; color: var(--fd-text-muted); font-size: 0.83rem; line-height: 1.55; }
.fd-matchup-line { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 14px; color: var(--fd-text); font-size: 1.2rem; }
.fd-matchup-line span { color: var(--fd-orange); font-family: var(--fd-font-sport); }

.fd-metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 24px; }
.fd-metric-card { position: relative; overflow: hidden; min-height: 154px; padding: 22px; border: 1px solid var(--fd-border); border-radius: var(--fd-radius-lg); background: linear-gradient(145deg, rgba(23,28,37,0.78), rgba(13,17,24,0.95)); box-shadow: var(--fd-shadow-sm); transition: transform var(--fd-transition), border-color var(--fd-transition), box-shadow var(--fd-transition); }
.fd-metric-card:hover { transform: translateY(-4px); border-color: var(--fd-border-strong); box-shadow: var(--fd-shadow-md); }
.fd-metric-card::after { content: ""; position: absolute; top: -55px; right: -42px; width: 110px; height: 110px; border-radius: 50%; background: var(--fd-metric-accent, rgba(59,130,246,0.12)); filter: blur(13px); pointer-events: none; }
.fd-metric-label { color: var(--fd-text-muted); font-size: 0.75rem; font-weight: 650; }
.fd-metric-value { margin-top: 17px; color: var(--fd-text); font-family: var(--fd-font-mono); font-size: clamp(1.8rem, 3vw, 2.65rem); font-weight: 770; line-height: 1; letter-spacing: -0.055em; }
.fd-metric-footer { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 15px; color: var(--fd-text-muted); font-size: 0.75rem; }
.fd-metric-delta { font-size: 0.72rem; font-weight: 660; }
.fd-delta-positive { color: var(--fd-green); }
.fd-delta-negative { color: var(--fd-red); }
.fd-delta-neutral { color: var(--fd-text-muted); }

.fd-action-card { position: relative; overflow: hidden; padding: 20px 22px; margin-bottom: 12px; border: 1px solid var(--fd-border); border-left: 3px solid var(--fd-action-color, var(--fd-blue)); border-radius: var(--fd-radius-md); background: linear-gradient(90deg, var(--fd-action-background, var(--fd-blue-soft)), rgba(17,21,29,0.85) 34%); transition: transform var(--fd-transition), border-color var(--fd-transition); }
.fd-action-card:hover { transform: translateX(3px); border-color: var(--fd-border-strong); border-left-color: var(--fd-action-color, var(--fd-blue)); }
.fd-action-priority { color: var(--fd-action-color, var(--fd-blue)); font-size: 0.65rem; font-weight: 790; letter-spacing: 0.12em; text-transform: uppercase; }
.fd-action-title { margin-top: 6px; color: var(--fd-text); font-size: 1rem; font-weight: 710; }
.fd-action-copy { margin-top: 6px; color: var(--fd-text-muted); font-size: 0.83rem; line-height: 1.5; }
.fd-action-impact { margin-top: 11px; color: var(--fd-text-soft); font-family: var(--fd-font-mono); font-size: 0.77rem; }

.fd-player-card { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 16px; padding: 18px; margin-bottom: 10px; border: 1px solid var(--fd-border); border-radius: var(--fd-radius-md); background: rgba(17,21,29,0.78); transition: transform var(--fd-transition), background var(--fd-transition), border-color var(--fd-transition); }
.fd-player-card:hover { transform: translateY(-2px); background: rgba(23,28,37,0.91); border-color: var(--fd-border-strong); }
.fd-player-avatar { width: 52px; height: 52px; overflow: hidden; display: grid; place-items: center; color: var(--fd-text-soft); border: 1px solid var(--fd-border); border-radius: 15px; background: var(--fd-surface-3); font-family: var(--fd-font-sport); font-weight: 850; }
.fd-player-name { color: var(--fd-text); font-weight: 710; }
.fd-player-meta { margin-top: 4px; color: var(--fd-text-muted); font-size: 0.74rem; }
.fd-player-numbers { display: flex; align-items: center; gap: 18px; }
.fd-player-stat { min-width: 58px; text-align: right; }
.fd-player-stat-label { color: var(--fd-text-faint); font-size: 0.61rem; letter-spacing: 0.06em; text-transform: uppercase; }
.fd-player-stat-value { margin-top: 4px; color: var(--fd-text); font-family: var(--fd-font-mono); font-size: 0.87rem; font-weight: 710; }

.fd-badge { display: inline-flex; align-items: center; justify-content: center; gap: 6px; width: fit-content; padding: 5px 9px; border: 1px solid transparent; border-radius: var(--fd-radius-pill); font-size: 0.63rem; font-weight: 790; letter-spacing: 0.07em; line-height: 1; text-transform: uppercase; white-space: nowrap; }
.fd-badge-start,.fd-badge-live,.fd-badge-positive { color: var(--fd-green); border-color: rgba(74,222,128,0.18); background: var(--fd-green-soft); }
.fd-badge-hold,.fd-badge-info { color: #60A5FA; border-color: rgba(59,130,246,0.18); background: var(--fd-blue-soft); }
.fd-badge-watch,.fd-badge-cached { color: var(--fd-gold); border-color: rgba(251,191,36,0.18); background: var(--fd-gold-soft); }
.fd-badge-trade { color: #FB923C; border-color: rgba(249,115,22,0.18); background: var(--fd-orange-soft); }
.fd-badge-drop,.fd-badge-danger,.fd-badge-unavailable { color: #F87171; border-color: rgba(239,68,68,0.18); background: var(--fd-red-soft); }
.fd-badge-simulation,.fd-badge-model { color: #A78BFA; border-color: rgba(139,92,246,0.18); background: var(--fd-purple-soft); }

.fd-section-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; margin: 32px 0 16px; }
.fd-section-title { color: var(--fd-text); font-size: 1.05rem; font-weight: 730; }
.fd-section-description { margin-top: 5px; color: var(--fd-text-muted); font-size: 0.77rem; }

.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button { min-height: 42px; padding: 0 18px; color: var(--fd-text); border: 1px solid var(--fd-border-strong); border-radius: 12px; background: linear-gradient(180deg, rgba(28,34,45,0.97), rgba(17,21,29,0.97)); box-shadow: var(--fd-shadow-sm); font-weight: 660; transition: transform var(--fd-transition), border-color var(--fd-transition), box-shadow var(--fd-transition), filter var(--fd-transition); }
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.20); box-shadow: var(--fd-shadow-md); }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { color: #071009; border-color: rgba(74,222,128,0.30); background: linear-gradient(135deg, #86EFAC, var(--fd-green)); box-shadow: 0 8px 28px rgba(74,222,128,0.19); }

[data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input { color: var(--fd-text); border-color: var(--fd-border-strong) !important; border-radius: 12px !important; background: rgba(13,17,24,0.89) !important; box-shadow: none !important; transition: border-color var(--fd-transition), box-shadow var(--fd-transition); }
[data-baseweb="input"] > div:focus-within, [data-baseweb="select"] > div:focus-within, [data-testid="stTextArea"] textarea:focus, [data-testid="stNumberInput"] input:focus { border-color: rgba(249,115,22,0.62) !important; box-shadow: 0 0 0 3px rgba(249,115,22,0.10) !important; }
input::placeholder, textarea::placeholder { color: var(--fd-text-faint) !important; }

[data-baseweb="tab-list"] { gap: 6px; padding: 4px; border: 1px solid var(--fd-border); border-radius: 13px; background: rgba(13,17,24,0.77); }
[data-baseweb="tab"] { min-height: 38px; padding: 0 14px; color: var(--fd-text-muted); border-radius: 9px; font-size: 0.8rem; font-weight: 630; }
[data-baseweb="tab"][aria-selected="true"] { color: var(--fd-text); background: rgba(255,255,255,0.07); }
[data-baseweb="tab-highlight"] { display: none; }
[data-testid="stExpander"] { overflow: hidden; border: 1px solid var(--fd-border) !important; border-radius: var(--fd-radius-md) !important; background: rgba(17,21,29,0.59); }
[data-testid="stExpander"] summary { color: var(--fd-text-soft); font-weight: 630; }
[data-testid="stMetric"] { padding: 18px; border: 1px solid var(--fd-border); border-radius: var(--fd-radius-md); background: rgba(17,21,29,0.73); }
[data-testid="stMetricLabel"] { color: var(--fd-text-muted); }
[data-testid="stMetricValue"] { color: var(--fd-text); font-family: var(--fd-font-mono); letter-spacing: -0.04em; }
[data-testid="stDataFrame"] { overflow: hidden; border: 1px solid var(--fd-border); border-radius: var(--fd-radius-md); background: var(--fd-surface); }

.fd-state { padding: 20px; border: 1px solid var(--fd-border); border-radius: var(--fd-radius-md); background: rgba(17,21,29,0.73); }
.fd-state-title { color: var(--fd-text); font-weight: 710; }
.fd-state-copy { margin-top: 6px; color: var(--fd-text-muted); font-size: 0.82rem; line-height: 1.55; }
.fd-state-warning { border-color: rgba(251,191,36,0.18); background: linear-gradient(90deg, var(--fd-gold-soft), rgba(17,21,29,0.73) 36%); }
.fd-state-danger { border-color: rgba(239,68,68,0.18); background: linear-gradient(90deg, var(--fd-red-soft), rgba(17,21,29,0.73) 36%); }

* { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.18) transparent; }
*::-webkit-scrollbar { width: 9px; height: 9px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb { border: 2px solid transparent; border-radius: 999px; background: rgba(255,255,255,0.16); background-clip: padding-box; }

@keyframes fd-page-enter { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fd-card-enter { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.fd-animate-in { animation: fd-card-enter 380ms cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.fd-delay-1 { animation-delay: 60ms; }
.fd-delay-2 { animation-delay: 120ms; }
.fd-delay-3 { animation-delay: 180ms; }
.fd-delay-4 { animation-delay: 240ms; }

@media (max-width: 1100px) {
  .fd-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fd-feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .block-container { padding: 1.2rem 1rem 3rem; }
  .fd-page-header { display: block; }
  .fd-page-meta { justify-content: flex-start; margin-top: 16px; }
  .fd-stadium-hero { min-height: 450px; padding: 50px 18px 38px; border-radius: 18px; }
  .fd-hero-title { font-size: clamp(2.45rem, 14vw, 4.5rem); }
  .fd-hero-description { font-size: 0.9rem; }
  .fd-hero-actions { flex-direction: column; }
  .fd-metric-grid, .fd-feature-grid { grid-template-columns: 1fr; }
  .fd-player-card { grid-template-columns: auto minmax(0, 1fr); }
  .fd-player-numbers { grid-column: 1 / -1; justify-content: space-between; padding-top: 12px; border-top: 1px solid var(--fd-border); }
  .fd-player-stat { text-align: left; }
  .fd-card { padding: 19px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
"""


def inject_global_styles() -> None:
    st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)

