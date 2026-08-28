"""
ThermoPulse AI — Streamlit Dashboard & Copilot Interface (Phase 4)

Run with:  streamlit run app.py

Two views:
  - Risk Map: search a place by name (or enter coordinates manually), pick a
    date/time, run a live Heat Risk assessment, see it on an interactive map
    with metric cards, a detail table, and a PDF triage report button.
  - AI Copilot: chat with the LangGraph agent directly.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os

import streamlit as st

# Bridge Streamlit Cloud's secrets manager into os.environ so the existing
# FortyGuardConfig/agent code (which reads via os.environ.get) works
# unchanged whether running locally (.env file, no secrets.toml) or
# deployed (st.secrets, backed by a real secrets.toml). We only touch
# st.secrets if a secrets file actually exists, since accessing it at all
# raises when none is present (as it does for local .env-based runs).
import pathlib

_secrets_paths = [
    pathlib.Path.home() / ".streamlit" / "secrets.toml",
    pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml",
]

if any(p.exists() for p in _secrets_paths):
    for _key in (
        "FORTYGUARD_API_KEY", "FORTYGUARD_BASE_URL", "LLM_PROVIDER",
        "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "GOOGLE_API_KEY",
        "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
    ):
        if _key in st.secrets and _key not in os.environ:
            os.environ[_key] = st.secrets[_key]

import pandas as pd
import pydeck as pdk
import requests

from dashboard_theme import RISK_RGB, hero, inject_theme, metric_card, risk_badge
from fortyguard import FortyGuardClient, FortyGuardBadRequestError, polygon_from_bbox
from spatial_engine import HeatRiskEngine

st.set_page_config(page_title="ThermoPulse AI", page_icon="🌡️", layout="wide")
inject_theme()

TODAY = dt.date.today()
DATE_MIN = dt.date(2019, 1, 1)
DATE_MAX = TODAY + dt.timedelta(days=1)  # FortyGuard allows ~12h into the future


def run_async(coro):
    """Run an async coroutine from Streamlit's synchronous callback context."""
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Place-name search (OpenStreetMap Nominatim — free, no API key required)
# --------------------------------------------------------------------------- #

def geocode_search(query: str, limit: int = 5):
    """
    Return up to `limit` candidate place matches (not just the first blind guess).
    Retries automatically on transient failures (Nominatim is a free public
    service and occasionally rate-limits or times out under load) before
    giving up, so a one-off hiccup doesn't require a manual re-click.
    """
    import time

    last_error = None
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": limit, "addressdetails": 1},
                headers={"User-Agent": "ThermoPulseAI-Hackathon/1.0"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))  # 1.5s, then 3s backoff
    return []


def bounds_from_point(lat: float, lon: float, display_name: str):
    half = 0.006  # ~650m half-width -> ~1.3km x 1.3km box
    return {
        "min_lat": lat - half, "max_lat": lat + half,
        "min_lon": lon - half, "max_lon": lon + half,
        "display_name": display_name,
    }


# --------------------------------------------------------------------------- #
# Risk assessment
# --------------------------------------------------------------------------- #

async def _run_assessment(min_lon, min_lat, max_lon, max_lat, date, hour, top_n):
    aoi = polygon_from_bbox(min_lon, min_lat, max_lon, max_lat)
    async with FortyGuardClient() as client:
        heatmap = await client.create_heatmap(
            polygon_aoi=aoi, start_date=date, filter_type=1, start_time=hour, granularity=100,
        )
        engine = HeatRiskEngine(client)
        assessments = await engine.assess_area(
            heatmap_result=heatmap, start_date=date, filter_type=1, start_time=hour,
            top_n_hottest=top_n,
        )
    return HeatRiskEngine.to_dataframe(assessments)


async def _generate_pdf(lat, lon, temperature, date):
    os.makedirs("reports", exist_ok=True)
    output_path = os.path.join("reports", f"triage_{lat:.4f}_{lon:.4f}_{date}.pdf")
    async with FortyGuardClient() as client:
        result = await client.heat_intelligence(
            latitude=lat, longitude=lon, temperature=temperature,
            date_=date, analysis=["environmental", "urban"],
        )
        return await client.download_heat_intelligence_pdf(result, output_path=output_path)


def render_risk_map_tab():
    hero("ThermoPulse AI", "Autonomous Heat Intelligence & Urban Resilience Copilot")

    with st.sidebar:
        st.markdown("### 📍 Location")
        place_query = st.text_input(
            "Search a place", value="Manhattan, New York",
            help="City, neighborhood, or landmark name. We'll assess a ~1.3km area around it.",
        )
        if st.button("🔍 Find this place", use_container_width=True):
            results = geocode_search(place_query)
            if results:
                st.session_state["geo_candidates"] = results
            else:
                st.session_state["geo_candidates"] = []
                st.warning("Couldn't find that place. Try adding a country, e.g. 'Alexandria, Egypt'.")

        candidates = st.session_state.get("geo_candidates")
        if candidates:
            labels = [c.get("display_name", "?") for c in candidates]
            choice_idx = st.selectbox(
                "Confirm the correct match:", options=range(len(labels)),
                format_func=lambda i: labels[i][:70],
            )
            chosen = candidates[choice_idx]
            st.session_state["geo_bounds"] = bounds_from_point(
                float(chosen["lat"]), float(chosen["lon"]), chosen.get("display_name", place_query),
            )
            st.caption(f"✅ Using: {labels[choice_idx][:70]}")

        defaults = st.session_state.get("geo_bounds", {
            "min_lat": 40.705, "max_lat": 40.718, "min_lon": -74.017, "max_lon": -74.003,
        })

        with st.expander("Advanced: manual coordinates", expanded=False):
            col1, col2 = st.columns(2)
            min_lat = col1.number_input("Min latitude", value=defaults["min_lat"], format="%.5f")
            max_lat = col2.number_input("Max latitude", value=defaults["max_lat"], format="%.5f")
            min_lon = col1.number_input("Min longitude", value=defaults["min_lon"], format="%.5f")
            max_lon = col2.number_input("Max longitude", value=defaults["max_lon"], format="%.5f")

        st.markdown("### 🕐 Date & Time")
        selected_date = st.date_input(
            "Date", value=dt.date(2024, 7, 15), min_value=DATE_MIN, max_value=DATE_MAX,
            help="FortyGuard covers 2019-01-01 through ~12 hours ahead of now.",
        )
        selected_time = st.time_input("Hour", value=dt.time(14, 0))
        date_str = selected_date.isoformat()
        hour_str = selected_time.strftime("%H:%M")

        top_n = st.slider("Points to assess", min_value=3, max_value=15, value=6,
                           help="More points = more API credit usage.")

        run_clicked = st.button("🌡️ Run Heat Risk Assessment", use_container_width=True)

    if run_clicked:
        with st.spinner("Generating heatmap and scoring risk points..."):
            try:
                df = run_async(_run_assessment(min_lon, min_lat, max_lon, max_lat, date_str, hour_str, top_n))
                if df.empty:
                    st.warning(
                        "No data returned for this area/time. Try a different location, "
                        "or a date further in the past (very recent/future dates sometimes "
                        "have sparse coverage)."
                    )
                else:
                    st.session_state["risk_df"] = df
                    st.session_state["risk_date"] = date_str
            except FortyGuardBadRequestError as e:
                st.error(
                    f"FortyGuard rejected this request: {e.message}. "
                    "Check the date is within 2019-01-01 to ~12 hours from now."
                )
            except Exception as e:
                st.error(f"Assessment failed: {e}")

    df: pd.DataFrame = st.session_state.get("risk_df")

    if df is None or df.empty:
        st.info("Search a place (or enter coordinates) in the sidebar, then click **Run Heat Risk Assessment**.")
        return

    # --- Metric cards ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("Highest Risk Score", f"{df['risk_score'].max():.0f}/100"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("Avg Risk Score", f"{df['risk_score'].mean():.0f}/100"), unsafe_allow_html=True)
    with c3:
        critical_count = (df["risk_category"] == "Critical").sum()
        st.markdown(metric_card("Critical Points", str(critical_count)), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("Points Assessed", str(len(df))), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Map (CARTO basemap — free, no API token needed) ---
    map_df = df.copy()
    map_df["color"] = map_df["risk_category"].map(RISK_RGB)
    map_df["radius"] = 15 + (map_df["risk_score"] / 100) * 35

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[longitude, latitude]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.85,
    )
    view_state = pdk.ViewState(
        latitude=map_df["latitude"].mean(), longitude=map_df["longitude"].mean(),
        zoom=15, pitch=0,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer], initial_view_state=view_state,
        map_provider="carto", map_style="dark",
        tooltip={"text": "{risk_category} risk — {risk_score} / 100\n{temperature_c}°C"},
    ))

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Detail table ---
    st.markdown("#### Risk Point Details")
    for _, row in df.iterrows():
        badge = risk_badge(row["risk_category"])
        st.markdown(
            f"""<div class="tp-card" style="margin-bottom:10px;">
                <b>({row['latitude']:.5f}, {row['longitude']:.5f})</b>
                &nbsp; {badge} &nbsp; <b>{row['risk_score']:.0f}/100</b>
                <div style="color:#94A3B8; margin-top:6px; font-size:0.9rem;">{row['explanation']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # --- PDF triage report ---
    st.markdown("<br>", unsafe_allow_html=True)
    top_row = df.iloc[0]
    if st.button("📄 Generate Official PDF Report for Riskiest Point", use_container_width=True):
        with st.spinner("Generating FortyGuard Heat Intelligence report (can take a few minutes)..."):
            try:
                pdf_path = run_async(_generate_pdf(
                    top_row["latitude"], top_row["longitude"], top_row["temperature_c"],
                    st.session_state.get("risk_date", date_str),
                ))
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download PDF Report", data=f.read(),
                        file_name=os.path.basename(pdf_path), mime="application/pdf",
                        use_container_width=True,
                    )
            except Exception as e:
                st.error(f"Report generation failed: {e}")


# --------------------------------------------------------------------------- #
# AI Copilot tab
# --------------------------------------------------------------------------- #

def render_copilot_tab():
    hero("ThermoPulse Copilot", "Ask about heat risk, routes, or request a formal report.")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "agent" not in st.session_state:
        from agent import build_agent
        st.session_state["agent"] = build_agent()

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("e.g. Which part of downtown is hottest right now?")
    if prompt:
        st.session_state["chat_history"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    result = run_async(
                        st.session_state["agent"].ainvoke({"messages": st.session_state["chat_history"]})
                    )
                    answer = result["messages"][-1].content
                except Exception as e:
                    answer = f"Sorry, something went wrong: {e}"
                st.markdown(answer)

        st.session_state["chat_history"].append({"role": "assistant", "content": answer})


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

tab1, tab2 = st.tabs(["🗺️ Risk Map", "💬 AI Copilot"])
with tab1:
    render_risk_map_tab()
with tab2:
    render_copilot_tab()