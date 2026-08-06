from __future__ import annotations

import streamlit as st


PRIMARY_PAGES = ("Home", "My Team", "Players", "League", "Settings")


def focused_pages(include_draft: bool = False) -> list[str]:
    pages = list(PRIMARY_PAGES)
    if include_draft:
        pages.append("Draft")
    return pages


def render_navigation(
    team_name: str,
    league_name: str,
    week: int | str,
    mode_label: str,
    include_draft: bool = False,
    available_pages: list[str] | None = None,
) -> str:
    from .components import brand_mark, freshness_badge
    from .formatting import h

    st.markdown(
        f"""
        <div class="fd-brand">
          {brand_mark()}
          <div>
            <div class="fd-brand-name">Fourth Down</div>
            <div class="fd-brand-subtitle">{h(league_name)} | Week {h(week)}</div>
          </div>
        </div>
        <div class="fd-sidebar-context">
          <div class="fd-sidebar-team">{h(team_name)}</div>
          {freshness_badge(mode_label)}
        </div>
        <div class="fd-nav-label">Workspace</div>
        """,
        unsafe_allow_html=True,
    )
    return st.radio(
        "Section",
        available_pages or focused_pages(include_draft),
        label_visibility="collapsed",
    )
