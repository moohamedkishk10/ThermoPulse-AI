"""
ThermoPulse AI — Refined Dark Slate Theme for Streamlit.

Designed for high contrast, maximum legibility, and zero eye-strain.
"""

from __future__ import annotations

import streamlit as st

COLORS = {
    "bg": "#0F172A",         # Deep Slate Blue (مريح للعين جداً ومظلم)
    "bg_panel": "#1E293B",   # Dark Slate Panel للـ Sidebar والبطاقات
    "border": "#334155",     # حد واضح ونظيف
    "text": "#F8FAFC",       # أبيض ناصع للكلام عشان يظهر بوضوح تام
    "text_dim": "#94A3B8",   # رمادي فاتح للنصوص الفرعية
    "cool": "#38BDF8",       # أزرق سماوي واضح (Low risk)
    "teal": "#2DD4BF",       # تركواز للـ Accent
    "amber": "#FBBF24",      # أصفر ذهبي واضح (Moderate risk)
    "orange": "#FB923C",     # برتقالي داكن (High risk)
    "hot": "#F87171",        # أحمر ناري واضح (Critical risk)
}

RISK_COLORS = {
    "Low": COLORS["cool"],
    "Moderate": COLORS["amber"],
    "High": COLORS["orange"],
    "Critical": COLORS["hot"],
}

# RGB tuples for pydeck
RISK_RGB = {
    "Low": [56, 189, 248, 220],
    "Moderate": [251, 191, 36, 220],
    "High": [251, 146, 60, 230],
    "Critical": [248, 113, 113, 240],
}


def inject_theme() -> None:
    """Call once near the top of the app to apply the high-contrast Dark theme."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', sans-serif;
            color: {COLORS['text']};
        }}

        /* Dark Slate Base Background */
        .stApp {{
            background-color: {COLORS['bg']};
            color: {COLORS['text']};
        }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background-color: {COLORS['bg_panel']};
            border-right: 1px solid {COLORS['border']};
        }}

        #MainMenu, footer {{ visibility: hidden; }}
        header {{ background: transparent; }}

        /* Hero Header */
        .tp-hero {{
            display: flex;
            align-items: baseline;
            gap: 10px;
            margin-bottom: 4px;
        }}
        .tp-hero-title {{
            font-size: 2.4rem;
            font-weight: 800;
            background: linear-gradient(90deg, {COLORS['teal']} 0%, {COLORS['cool']} 40%, {COLORS['amber']} 75%, {COLORS['hot']} 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.02em;
        }}
        .tp-hero-sub {{
            color: {COLORS['text_dim']};
            font-size: 0.95rem;
            font-weight: 500;
            margin-bottom: 1.8rem;
        }}

        /* Solid High-Contrast Cards */
        .tp-card {{
            background-color: {COLORS['bg_panel']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
            padding: 18px 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }}

        .tp-metric-label {{
            color: {COLORS['text_dim']};
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }}
        .tp-metric-value {{
            font-size: 2.1rem;
            font-weight: 800;
            color: {COLORS['text']} !important;
            letter-spacing: -0.02em;
        }}

        /* High-Legibility Badges */
        .tp-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.03em;
        }}

        /* Solid Action Buttons */
        div.stButton > button {{
            background: linear-gradient(90deg, {COLORS['cool']}, {COLORS['teal']});
            color: #0F172A !important;
            font-weight: 700;
            border: none;
            border-radius: 8px;
            padding: 0.6rem 1.4rem;
        }}
        div.stButton > button:hover {{
            filter: brightness(1.15);
            cursor: pointer;
        }}

        /* Chat Input Area Fix */
        .main .block-container {{
            padding-bottom: 120px;
        }}

        div[data-testid="stChatInput"] {{
            position: fixed;
            bottom: 0;
            left: 22rem;
            right: 2rem;
            z-index: 999;
            background-color: {COLORS['bg_panel']};
            padding: 16px 14px;
            border-top: 1px solid {COLORS['border']};
        }}

        section[data-testid="stSidebar"][aria-expanded="false"] ~ div div[data-testid="stChatInput"] {{
            left: 2rem;
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
    """Return an HTML badge span with high contrast background."""
    color = RISK_COLORS.get(category, COLORS["text_dim"])
    return f'<span class="tp-badge" style="background:{color}2B; color:{color}; border:1px solid {color};">{category}</span>'


def metric_card(label: str, value: str) -> str:
    """Return a clean, high-contrast metric card."""
    return f"""
    <div class="tp-card">
        <div class="tp-metric-label">{label}</div>
        <div class="tp-metric-value">{value}</div>
    </div>
    """