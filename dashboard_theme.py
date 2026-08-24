"""
ThermoPulse AI — visual identity for the Streamlit dashboard.

A dedicated theme (not tied to any external brand): dark, professional
background with a thermal gradient — cool blue for low risk shading up
through amber to hot red for critical risk — used consistently across the
map, badges, and metric cards so the color itself carries meaning.
"""

from __future__ import annotations

import streamlit as st

COLORS = {
    "bg": "#0B1120",
    "bg_panel": "#111A2E",
    "border": "#1E293B",
    "text": "#E2E8F0",
    "text_dim": "#94A3B8",
    "cool": "#3B82F6",     # Low risk
    "teal": "#06B6D4",     # accent / brand
    "amber": "#F59E0B",    # Moderate risk
    "orange": "#F97316",   # High risk
    "hot": "#EF4444",      # Critical risk
}

RISK_COLORS = {
    "Low": COLORS["cool"],
    "Moderate": COLORS["amber"],
    "High": COLORS["orange"],
    "Critical": COLORS["hot"],
}

# RGB tuples for pydeck (which wants [r, g, b, alpha], not hex strings)
RISK_RGB = {
    "Low": [59, 130, 246, 200],
    "Moderate": [245, 158, 11, 200],
    "High": [249, 115, 22, 210],
    "Critical": [239, 68, 68, 230],
}


def inject_theme() -> None:
    """Call once near the top of the app to apply the ThermoPulse look."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', sans-serif;
        }}

        .stApp {{
            background: linear-gradient(180deg, {COLORS['bg']} 0%, #0A0E1A 100%);
            color: {COLORS['text']};
        }}

        section[data-testid="stSidebar"] {{
            background: {COLORS['bg_panel']};
            border-right: 1px solid {COLORS['border']};
        }}

        #MainMenu, footer {{ visibility: hidden; }}
        header {{ background: transparent; }}

        .tp-hero {{
            display: flex;
            align-items: baseline;
            gap: 10px;
            margin-bottom: 4px;
        }}
        .tp-hero-title {{
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(90deg, {COLORS['cool']} 0%, {COLORS['teal']} 35%, {COLORS['amber']} 70%, {COLORS['hot']} 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.02em;
        }}
        .tp-hero-sub {{
            color: {COLORS['text_dim']};
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
        }}

        .tp-card {{
            background: {COLORS['bg_panel']};
            border: 1px solid {COLORS['border']};
            border-radius: 14px;
            padding: 18px 20px;
        }}

        .tp-metric-label {{
            color: {COLORS['text_dim']};
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }}
        .tp-metric-value {{
            font-size: 1.9rem;
            font-weight: 700;
            color: {COLORS['text']};
        }}

        .tp-badge {{
            display: inline-block;
            padding: 3px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}

        div.stButton > button {{
            background: linear-gradient(90deg, {COLORS['cool']}, {COLORS['teal']});
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            padding: 0.5rem 1.2rem;
        }}
        div.stButton > button:hover {{
            filter: brightness(1.1);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str = "ThermoPulse AI", subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="tp-hero"><span class="tp-hero-title">{title}</span></div>
        <div class="tp-hero-sub">{subtitle}</div>
        """,
        unsafe_allow_html=True,
    )


def risk_badge(category: str) -> str:
    """Return an HTML badge span for a risk category (embed with unsafe_allow_html)."""
    color = RISK_COLORS.get(category, COLORS["text_dim"])
    return f'<span class="tp-badge" style="background:{color}22; color:{color}; border:1px solid {color}66;">{category}</span>'


def metric_card(label: str, value: str) -> str:
    """Return an HTML metric card (embed with unsafe_allow_html)."""
    return f"""
    <div class="tp-card">
        <div class="tp-metric-label">{label}</div>
        <div class="tp-metric-value">{value}</div>
    </div>
    """