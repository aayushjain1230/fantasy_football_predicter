from __future__ import annotations

from textwrap import dedent
from typing import Any

import streamlit as st

from .formatting import fantasy_points, h, percentage, percentage_points


BADGE_CLASS = {
    "START": "fd-badge-start",
    "HOLD": "fd-badge-hold",
    "WATCH": "fd-badge-watch",
    "TRADE": "fd-badge-trade",
    "DROP": "fd-badge-drop",
    "LIVE": "fd-badge-live",
    "CACHED": "fd-badge-cached",
    "STALE": "fd-badge-watch",
    "DEMO": "fd-badge-model",
    "UNAVAILABLE": "fd-badge-unavailable",
    "HIGH": "fd-badge-start",
    "MEDIUM": "fd-badge-watch",
    "LOW": "fd-badge-danger",
}


def brand_mark() -> str:
    return '<div class="fd-brand-mark">4D</div>'


def badge(label: str, kind: str | None = None) -> str:
    key = (kind or label or "INFO").upper()
    klass = BADGE_CLASS.get(key, "fd-badge-info")
    return f'<span class="fd-badge {klass}">{h(label)}</span>'


def recommendation_badge(label: str) -> str:
    return badge(label, label)


def confidence_badge(label: str | float | None) -> str:
    if isinstance(label, (int, float)):
        text = "High" if label >= 0.75 else "Medium" if label >= 0.5 else "Low"
    else:
        text = str(label or "Medium")
    return badge(text, text)


def freshness_badge(label: str) -> str:
    return badge(label, label)


def page_header(title: str, eyebrow: str, subtitle: str = "", meta: list[str] | None = None) -> None:
    meta_html = "".join(meta or [])
    st.markdown(
        f"""
        <section class="fd-page-header">
          <div>
            <div class="fd-page-eyebrow">{h(eyebrow)}</div>
            <h1 class="fd-page-title">{h(title)}</h1>
            <div class="fd-page-subtitle">{h(subtitle)}</div>
          </div>
          <div class="fd-page-meta">{meta_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, description: str = "", right: str = "") -> None:
    st.markdown(
        f"""
        <div class="fd-section-header">
          <div>
            <div class="fd-section-title">{h(title)}</div>
            <div class="fd-section-description">{h(description)}</div>
          </div>
          <div>{right}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str | float | int | None, footer: str = "", tone: str = "blue", delta: str = "") -> str:
    accent = {
        "green": "var(--fd-green-soft)",
        "blue": "var(--fd-blue-soft)",
        "gold": "var(--fd-gold-soft)",
        "orange": "var(--fd-orange-soft)",
        "red": "var(--fd-red-soft)",
        "purple": "var(--fd-purple-soft)",
    }.get(tone, "var(--fd-blue-soft)")
    delta_class = "fd-delta-positive" if str(delta).startswith("+") else "fd-delta-negative" if str(delta).startswith("-") else "fd-delta-neutral"
    return f"""
    <div class="fd-metric-card fd-animate-in" style="--fd-metric-accent:{accent};">
      <div class="fd-metric-label">{h(label)}</div>
      <div class="fd-metric-value">{h(value)}</div>
      <div class="fd-metric-footer">
        <span>{h(footer)}</span>
        <span class="fd-metric-delta {delta_class}">{h(delta)}</span>
      </div>
    </div>
    """


def metric_grid(cards: list[str]) -> None:
    if not cards:
        return
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        col.markdown(dedent(card).strip(), unsafe_allow_html=True)


def action_card(action: Any) -> None:
    priority = str(getattr(action, "priority", "Medium"))
    category = str(getattr(action, "category", "HOLD"))
    color = {
        "Critical": "var(--fd-red)",
        "High": "var(--fd-green)",
        "Medium": "var(--fd-gold)",
        "Low": "var(--fd-blue)",
        "Monitor": "var(--fd-gold)",
    }.get(priority, "var(--fd-blue)")
    background = {
        "Critical": "var(--fd-red-soft)",
        "High": "var(--fd-green-soft)",
        "Medium": "var(--fd-gold-soft)",
        "Low": "var(--fd-blue-soft)",
        "Monitor": "var(--fd-gold-soft)",
    }.get(priority, "var(--fd-blue-soft)")
    points = getattr(action, "expected_points_change", None)
    win = getattr(action, "win_probability_change", None)
    impact = "Impact unavailable"
    if points is not None:
        impact = f"{float(points):+.1f} expected points"
    if win is not None:
        impact += f" | {percentage_points(win)} win probability"
    st.markdown(
        f"""
        <article class="fd-action-card" style="--fd-action-color:{color}; --fd-action-background:{background};">
          <div class="fd-action-priority">{h(priority)} | {h(category)}</div>
          <div class="fd-action-title">{h(getattr(action, "recommended_action", ""))}</div>
          <div class="fd-action-copy">{h(getattr(action, "title", ""))}</div>
          <div class="fd-action-impact">{h(impact)} | {h(getattr(action, "confidence", "Medium"))} confidence</div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def player_card(player: Any, projection: Any | None = None) -> str:
    value = getattr(projection, "mean", getattr(player, "mean", None))
    initials = "".join(part[:1] for part in str(player.name).split()[:2]).upper()
    return f"""
    <div class="fd-player-card">
      <div class="fd-player-avatar">{h(initials)}</div>
      <div>
        <div class="fd-player-name">{h(player.name)}</div>
        <div class="fd-player-meta">{h(player.position)} | {h(player.team)} | {h(player.injury_status)}</div>
      </div>
      <div class="fd-player-numbers">
        <div class="fd-player-stat">
          <div class="fd-player-stat-label">Proj</div>
          <div class="fd-player-stat-value">{h(fantasy_points(value))}</div>
        </div>
        <div class="fd-player-stat">
          <div class="fd-player-stat-label">Avail</div>
          <div class="fd-player-stat-value">{h(percentage(getattr(player, "availability", None)))}</div>
        </div>
      </div>
    </div>
    """


def matchup_card(team: str, opponent: str, projected: float, win_probability: float) -> None:
    st.markdown(
        f"""
        <div class="fd-card fd-card-static">
          <div class="fd-card-label">Current Matchup</div>
          <div class="fd-matchup-line"><strong>{h(team)}</strong><span>vs</span><strong>{h(opponent)}</strong></div>
          <div class="fd-card-copy">Projected {h(fantasy_points(projected))} points | {h(percentage(win_probability))} win estimate</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def feature_tile(icon: str, label: str) -> str:
    return f"""
    <div class="fd-feature-tile">
      <div class="fd-feature-icon">{h(icon)}</div>
      <div class="fd-feature-label">{h(label)}</div>
    </div>
    """


def stadium_hero() -> None:
    tiles = "".join(
        [
            feature_tile("IR", "Injury status"),
            feature_tile("WX", "Game weather"),
            feature_tile("VS", "Opponent context"),
            feature_tile("VOR", "Draft & waivers"),
        ]
    )
    st.markdown(
        f"""
        <section class="fd-stadium-hero">
          <div class="fd-stadium-vignette"></div>
          <div class="fd-hero-content">
            <div class="fd-hero-kicker">Live inputs · Explainable models · No demo data</div>
            <h1 class="fd-hero-title">Smarter fantasy football<span class="fd-hero-title-accent">decisions on fourth down</span></h1>
            <p class="fd-hero-description">
              Connect your ESPN league. Fourth Down reads the real roster, free-agent pool, draft market, schedule, and provider context—then shows the decision and the evidence behind it.
            </p>
            <div class="fd-feature-grid">{tiles}</div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, copy: str) -> None:
    st.markdown(
        f'<div class="fd-state"><div class="fd-state-title">{h(title)}</div><div class="fd-state-copy">{h(copy)}</div></div>',
        unsafe_allow_html=True,
    )


def warning_state(title: str, copy: str) -> None:
    st.markdown(
        f'<div class="fd-state fd-state-warning"><div class="fd-state-title">{h(title)}</div><div class="fd-state-copy">{h(copy)}</div></div>',
        unsafe_allow_html=True,
    )
