"""
Heat Risk Engine — orchestration layer.

Combines two FortyGuard data sources for the same area/time:
  - Create Heatmap        -> per-tile temperature (GeoJSON grid)
  - Satellite Segmentation -> per-point land-cover class % (tree/building/road/...)

Satellite Segmentation only accepts a single lat/lon per call, so we can't
segment every heatmap tile (that would be one API call per tile — expensive
and slow). Instead we sample a bounded number of tiles (default: the
hottest N, since those are the ones worth explaining) and segment their
centroids concurrently via `satellite_segmentation_grid`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from datetime import date

import pandas as pd

from fortyguard import FortyGuardClient
from .scoring import DEFAULT_WEIGHTS, RiskBreakdown, RiskWeights, compute_heat_risk


@dataclass
class RiskAssessment:
    """One scored point: location, temperature, segmentation, and the resulting risk breakdown."""
    tile_id: Any
    latitude: float
    longitude: float
    temperature_c: float
    segments: Dict[str, float]
    risk: RiskBreakdown


class HeatRiskEngine:
    """
    Usage:
        async with FortyGuardClient() as client:
            engine = HeatRiskEngine(client)
            assessments = await engine.assess_area(
                heatmap_result=heatmap,
                start_date="2024-07-15", filter_type=1, start_time="14:00",
                top_n_hottest=8,
            )
            df = HeatRiskEngine.to_dataframe(assessments)
    """

    def __init__(self, client: FortyGuardClient, weights: RiskWeights = DEFAULT_WEIGHTS):
        self.client = client
        self.weights = weights

    async def assess_area(
        self,
        *,
        heatmap_result: Dict[str, Any],
        start_date: Union[str, date],
        filter_type: int,
        granularity: int = 100,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        top_n_hottest: int = 8,
    ) -> List[RiskAssessment]:
        """
        Score the `top_n_hottest` tiles from a completed create_heatmap() result.

        Sampling only the hottest tiles keeps API cost bounded and focuses the
        Risk Engine (and the Triage Report built on top of it) on the areas
        that actually matter for mitigation decisions.
        """
        tiles = _tiles_from_heatmap(heatmap_result)
        if not tiles:
            return []

        hottest = sorted(tiles, key=lambda t: t["average_temperature"], reverse=True)[:top_n_hottest]
        temps = [t["average_temperature"] for t in tiles]
        aoi_min, aoi_max = min(temps), max(temps)

        points = [(t["centroid_lat"], t["centroid_lon"]) for t in hottest]
        segmentation_results = await self.client.satellite_segmentation_grid(
            points=points,
            start_date=start_date,
            filter_type=filter_type,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time,
        )

        assessments: List[RiskAssessment] = []
        for tile, seg_result in zip(hottest, segmentation_results):
            segments = (seg_result.get("segmentation") or {}).get("segments", {}) or {}
            risk = compute_heat_risk(
                temperature_c=tile["average_temperature"],
                aoi_min_c=aoi_min,
                aoi_max_c=aoi_max,
                segments=segments,
                weights=self.weights,
            )
            assessments.append(
                RiskAssessment(
                    tile_id=tile["tile_id"],
                    latitude=tile["centroid_lat"],
                    longitude=tile["centroid_lon"],
                    temperature_c=tile["average_temperature"],
                    segments=segments,
                    risk=risk,
                )
            )

        return assessments

    @staticmethod
    @staticmethod
    def to_dataframe(assessments: List[RiskAssessment]) -> pd.DataFrame:
        """Flatten a list of RiskAssessment into a tidy DataFrame for the UI/map."""
        columns = [
            "tile_id", "latitude", "longitude", "temperature_c",
            "risk_score", "risk_category", "impervious_pct", "vegetation_pct", "explanation",
        ]
        if not assessments:
            return pd.DataFrame(columns=columns)

        rows = []
        for a in assessments:
            rows.append({
                "tile_id": a.tile_id,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "temperature_c": a.temperature_c,
                "risk_score": a.risk.score,
                "risk_category": a.risk.category,
                "impervious_pct": a.risk.impervious_pct,
                "vegetation_pct": a.risk.vegetation_pct,
                "explanation": a.risk.explain(),
            })
        return pd.DataFrame(rows).sort_values("risk_score", ascending=False).reset_index(drop=True)

def _tiles_from_heatmap(heatmap_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract {tile_id, average_temperature, centroid_lat, centroid_lon} from
    the raw map_data GeoJSON, without requiring geopandas (plain shapely-free
    centroid = average of the polygon's ring coordinates — sufficient for
    the small, roughly-square tiles FortyGuard returns).
    """
    features = (heatmap_result.get("map_data") or {}).get("features", [])
    tiles = []
    for feat in features:
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [[]])[0]
        if not coords:
            continue
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        tiles.append({
            "tile_id": props.get("tile_id"),
            "average_temperature": props.get("average_temperature"),
            "centroid_lon": sum(lons) / len(lons),
            "centroid_lat": sum(lats) / len(lats),
        })
    return tiles