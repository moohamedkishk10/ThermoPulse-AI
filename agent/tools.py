"""
Agent tools — each one wraps FortyGuardClient / HeatRiskEngine calls behind
a single async function the LLM can invoke. Every tool opens its own short-
lived FortyGuardClient session (simplest correct behavior for LangGraph's
tool-calling model, where each call is independent).

Three tools, matching the three agentic capabilities from the project plan:
  1. assess_heat_risk_area      -> Automated Microclimate Triage (data side)
  2. compare_route_options      -> Thermal-Aware Route Optimization
  3. generate_triage_report     -> Automated Microclimate Triage Report (PDF)
"""

from __future__ import annotations

import json
import os
from typing import List

from langchain_core.tools import tool

from fortyguard import FortyGuardClient, polygon_from_bbox
from spatial_engine import HeatRiskEngine

REPORTS_DIR = os.environ.get("THERMOPULSE_REPORTS_DIR", "reports")


@tool
async def assess_heat_risk_area(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float,
    date: str, hour: str, top_n_hottest: int = 5,
) -> str:
    """
    Assess heat risk across a rectangular area for a given date and hour.

    Generates a temperature heatmap, then scores the hottest points using
    the Heat Risk Index (temperature + impervious surface + vegetation
    deficit). Use this to answer questions like "which parts of this area
    are most at risk right now" or to identify candidates for a triage report.

    Args:
        min_lon, min_lat, max_lon, max_lat: Bounding box of the area (WGS84 degrees).
        date: Date in YYYY-MM-DD format.
        hour: Hour in HH:MM 24-hour format (e.g. "14:00").
        top_n_hottest: How many of the hottest points to score (default 5, keep small to limit API cost).

    Returns:
        A human-readable summary of the top risk points, ranked highest risk first.
    """
    aoi = polygon_from_bbox(min_lon, min_lat, max_lon, max_lat)

    async with FortyGuardClient() as client:
        heatmap = await client.create_heatmap(
            polygon_aoi=aoi, start_date=date, filter_type=1, start_time=hour, granularity=100,
        )
        engine = HeatRiskEngine(client)
        assessments = await engine.assess_area(
            heatmap_result=heatmap, start_date=date, filter_type=1, start_time=hour,
            top_n_hottest=top_n_hottest,
        )

    if not assessments:
        return "No heatmap tiles were returned for this area/time — check the coordinates and date."

    assessments.sort(key=lambda a: a.risk.score, reverse=True)
    lines = [f"Heat risk assessment for area ({min_lat},{min_lon}) to ({max_lat},{max_lon}) at {date} {hour}:"]
    for a in assessments:
        lines.append(f"- ({a.latitude:.5f}, {a.longitude:.5f}): {a.risk.explain()}")
    return "\n".join(lines)


@tool
async def compare_route_options(waypoints_json: str, date: str, hour: str) -> str:
    """
    Compare thermal comfort across a set of candidate route waypoints and
    recommend the coolest option, for thermal-aware pedestrian/delivery routing.

    Args:
        waypoints_json: JSON string of a list of named candidate routes, each
            a list of [lat, lon] points, e.g.:
            '{"Route A": [[40.71,-74.01],[40.712,-74.008]], "Route B": [[40.709,-74.012],[40.711,-74.009]]}'
        date: Date in YYYY-MM-DD format.
        hour: Hour in HH:MM 24-hour format.

    Returns:
        A comparison of average apparent temperature (heat index) per route,
        with a recommendation for the coolest one.
    """
    try:
        routes: dict = json.loads(waypoints_json)
    except json.JSONDecodeError as e:
        return f"Could not parse waypoints_json: {e}"

    results = {}
    async with FortyGuardClient() as client:
        for route_name, points in routes.items():
            heat_indices = []
            for lat, lon in points:
                env = await client.environmental_parameters(
                    latitude=lat, longitude=lon, temperature=30.0,  # placeholder, API returns actual reading
                    start_date=date, filter_type=1, start_time=hour,
                    analysis=["heat_index_celsius"],
                )
                locs = env.get("locations") or []
                if locs:
                    values = locs[0].get("parameters", {}).get("heat_index_celsius", [])
                    values = [v for v in values if v is not None]
                    if values:
                        heat_indices.append(sum(values) / len(values))
            results[route_name] = sum(heat_indices) / len(heat_indices) if heat_indices else None

    lines = [f"Route thermal comfort comparison for {date} {hour}:"]
    for name, avg_heat_index in results.items():
        val = f"{avg_heat_index:.1f}°C avg heat index" if avg_heat_index is not None else "no data"
        lines.append(f"- {name}: {val}")

    valid = {k: v for k, v in results.items() if v is not None}
    if valid:
        best = min(valid, key=valid.get)
        lines.append(f"\nRecommendation: {best} is the coolest option ({valid[best]:.1f}°C avg heat index).")
    else:
        lines.append("\nNo valid data returned for any route.")

    return "\n".join(lines)


@tool
async def generate_triage_report(
    latitude: float, longitude: float, temperature: float, date: str,
    analysis: List[str] = ["environmental", "urban"],
) -> str:
    """
    Generate an official FortyGuard Heat Intelligence PDF report for a
    specific location — use this when a location's risk score crosses a
    concerning threshold and a city planner needs a formal document.

    Args:
        latitude, longitude: The location to report on.
        temperature: The observed/predicted temperature (°C) at this location and date.
        date: Date in YYYY-MM-DD format.
        analysis: Which Heat Intelligence categories to include
            (any of: geographic, environmental, urban, events, anthropogenic).

    Returns:
        The local file path where the PDF was saved, or an error message.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    safe_name = f"triage_{latitude:.4f}_{longitude:.4f}_{date}.pdf".replace(":", "-")
    output_path = os.path.join(REPORTS_DIR, safe_name)

    async with FortyGuardClient() as client:
        result = await client.heat_intelligence(
            latitude=latitude, longitude=longitude, temperature=temperature,
            date_=date, analysis=analysis,
        )
        saved_path = await client.download_heat_intelligence_pdf(result, output_path=output_path)

    return f"Triage report generated and saved to: {saved_path}"


ALL_TOOLS = [assess_heat_risk_area, compare_route_options, generate_triage_report]