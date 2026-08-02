from __future__ import annotations


CHART_COLORS = {
    "green": "#4ADE80",
    "blue": "#3B82F6",
    "gold": "#FBBF24",
    "orange": "#F97316",
    "red": "#EF4444",
    "purple": "#8B5CF6",
    "muted": "#5E6878",
}


FOURTH_DOWN_PLOTLY_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, sans-serif", "color": "#CBD5E1"},
    "margin": {"l": 20, "r": 20, "t": 44, "b": 20},
    "hoverlabel": {
        "bgcolor": "#171C25",
        "bordercolor": "rgba(255,255,255,0.10)",
        "font": {"color": "#F8FAFC"},
    },
    "legend": {"bgcolor": "rgba(0,0,0,0)"},
    "xaxis": {"gridcolor": "rgba(255,255,255,0.05)", "zerolinecolor": "rgba(255,255,255,0.08)"},
    "yaxis": {"gridcolor": "rgba(255,255,255,0.05)", "zerolinecolor": "rgba(255,255,255,0.08)"},
}


def apply_plotly_theme(fig):
    fig.update_layout(**FOURTH_DOWN_PLOTLY_LAYOUT)
    return fig

