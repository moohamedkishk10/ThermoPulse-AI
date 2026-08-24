"""
FortyGuard Temperature API(R) — Async Python Wrapper
=====================================================

Covers all 7 documented endpoints:
  - POST /heatmap          (Create Heatmap)
  - POST /satellite        (Satellite View Segmentation)
  - POST /streetview       (Street View Segmentation)
  - POST /heat_intelligence(Heat Intelligence -> PDF report)
  - POST /env_params       (Environmental Parameters)
  - GET  /status/{id}      (Check Status - shared polling endpoint)
  - POST /system/fetch-api-key-usage  (Check API Credits Usage)

Design notes
------------
* All "Analysis Endpoints" are asynchronous: POST submits a job and returns
  an `activity_id`; the actual result is retrieved by polling `Check Status`
  until `status` is a success/failure terminal value. A single
  `_poll_until_complete` method implements this once and is reused by every
  endpoint method.
* Every public method returns a plain dict (`result["data"]["result"]`) plus,
  where it makes sense, a helper to convert into a pandas DataFrame.
* Network errors and 5xx responses are retried with exponential backoff.
  4xx errors (bad request, auth) are NOT retried — they won't succeed on
  retry and should surface to the caller immediately.
* Nothing here ever logs or prints the API key or a Heat Intelligence
  download_link (those are temporary signed URLs).
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

import aiohttp
import pandas as pd

from .config import FortyGuardConfig
from .exceptions import (
    FortyGuardActivityFailedError,
    FortyGuardAuthError,
    FortyGuardBadRequestError,
    FortyGuardError,
    FortyGuardRateLimitError,
    FortyGuardServerError,
    FortyGuardTimeoutError,
)

logger = logging.getLogger("fortyguard")

AnalyticType = Literal["tcm", "time_of_measure", "exceedance", "persistence"]
Direction = Literal["above", "below"]
HeatIntelAnalysis = Literal["geographic", "environmental", "urban", "events", "anthropogenic"]

_ACTIVE_STATUSES = {"Processing", "Pending", "Queued", "Submitted", "Running"}
_TERMINAL_SUCCESS_VALUES = {"Completed", "succeeded", "completed"}
_TERMINAL_FAILURE_VALUES = {"Failed", "failed", "error"}

# Per the Participant Handbook (§7.7): heatmap AOIs are capped at ~130 km^2
# (50 mi^2). Larger polygons are rejected by FortyGuard - we check client-side
# first so the error is immediate and clear instead of a round-trip 400.
_MAX_HEATMAP_AREA_KM2 = 130.0


# --------------------------------------------------------------------------- #
# Small input helpers
# --------------------------------------------------------------------------- #

def _polygon_area_km2(polygon_aoi: Dict[str, Any]) -> float:
    """
    Rough area estimate (km^2) for a GeoJSON polygon, via the shoelace
    formula with a simple equirectangular approximation. This is a soft
    client-side guard (see _MAX_HEATMAP_AREA_KM2), not a precise geodesic
    calculation - it's accurate enough to catch "way too big" requests
    before they cost a round-trip 400 from FortyGuard.
    """
    try:
        coords = polygon_aoi["features"][0]["geometry"]["coordinates"][0]
    except (KeyError, IndexError, TypeError):
        return 0.0

    if len(coords) < 3:
        return 0.0

    avg_lat = sum(c[1] for c in coords) / len(coords)
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(avg_lat))

    area_deg2 = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        area_deg2 += x1 * y2 - x2 * y1
    area_deg2 = abs(area_deg2) / 2.0

    return area_deg2 * km_per_deg_lat * km_per_deg_lon


def polygon_from_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> Dict[str, Any]:
    """
    Build a FortyGuard-compatible `polygon_aoi` FeatureCollection from a
    simple bounding box. Convenience helper — callers can also pass their
    own GeoJSON FeatureCollection directly.
    """
    coords = [[
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": coords},
            }
        ],
    }


def _date_time_block(
    *,
    start_date: Union[str, date],
    filter_type: int,
    end_date: Optional[Union[str, date]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a `date_time` object matching FortyGuard's filter_type semantics:
      1 = Single Hour       (start_date, start_time)
      2 = Range of Hours    (start_date, start_time, end_time)
      3 = Single Day        (start_date only)
      4 = Range of Days     (start_date, end_date)  [heatmap only, <=1 month]
      5 = Single Month      (start_date only — UNCONFIRMED field requirements)
    """

    def _s(d: Union[str, date]) -> str:
        return d.isoformat() if isinstance(d, date) else d

    block: Dict[str, Any] = {"start_date": _s(start_date), "filter_type": filter_type}

    if filter_type == 1:
        if not start_time:
            raise ValueError("filter_type=1 (Single Hour) requires start_time")
        block["start_time"] = start_time
    elif filter_type == 2:
        if not (start_time and end_time):
            raise ValueError("filter_type=2 (Range of Hours) requires start_time and end_time")
        block["start_time"] = start_time
        block["end_time"] = end_time
    elif filter_type == 3:
        pass  # start_date only
    elif filter_type == 4:
        if not end_date:
            raise ValueError("filter_type=4 (Range of Days) requires end_date")
        block["end_date"] = _s(end_date)
    elif filter_type == 5:
        # Per the Participant Handbook (Sept 2026 update): 5 = Single Month.
        # UNCONFIRMED: exact required/optional fields for this value were not
        # in the endpoint docs we captured (only start_date was documented
        # for the original filter_type 1-4 set). Treating it like
        # filter_type=3 (start_date only) as the safest guess - flag this to
        # FortyGuard support if you rely on it for anything beyond a rough test.
        logger.warning(
            "filter_type=5 (Single Month) is used per the Participant Handbook, "
            "but its exact field requirements are unconfirmed. Proceeding with "
            "start_date only - verify behavior before relying on this in production."
        )
    else:
        raise ValueError(f"Unknown filter_type: {filter_type} (expected 1-5)")

    return block


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #

@dataclass
class ActivityHandle:
    """Lightweight handle returned immediately after a submit call."""
    activity_id: str
    endpoint: str


class FortyGuardClient:
    """
    Async client for the FortyGuard Temperature API(R).

    Usage:
        async with FortyGuardClient() as client:
            result = await client.create_heatmap(
                polygon_aoi=polygon_from_bbox(-74.017, 40.705, -74.003, 40.718),
                start_date="2024-07-15", filter_type=1, start_time="14:00",
                granularity=100,
            )
            df = client.heatmap_stats_to_dataframe(result)
    """

    def __init__(self, config: Optional[FortyGuardConfig] = None):
        self.config = config or FortyGuardConfig()
        self.config.validate()
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

    async def __aenter__(self) -> "FortyGuardClient":
        self._session = aiohttp.ClientSession(
            headers={"api-key": self.config.api_key, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout_seconds),
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError(
                "FortyGuardClient must be used as an async context manager: "
                "`async with FortyGuardClient() as client: ...`"
            )
        return self._session

    # --------------------------------------------------------------------- #
    # Low-level HTTP with retry/backoff
    # --------------------------------------------------------------------- #

    async def _request(
        self, method: str, path: str, *, json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        session = self._require_session()
        url = f"{self.config.base_url.rstrip('/')}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with self._semaphore:
                    async with session.request(method, url, json=json_body) as resp:
                        text = await resp.text()
                        body = _safe_json(text)

                        if resp.status == 200:
                            return body if isinstance(body, dict) else {"data": body}

                        if resp.status in (401, 403):
                            raise FortyGuardAuthError(
                                "FortyGuard rejected the API key (check FORTYGUARD_API_KEY).",
                                status_code=resp.status, payload=body,
                            )
                        if resp.status == 400:
                            raise FortyGuardBadRequestError(
                                body.get("message", "Bad request") if isinstance(body, dict) else "Bad request",
                                status_code=resp.status, payload=body,
                            )
                        if resp.status == 429:
                            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                            raise FortyGuardRateLimitError(
                                "Rate limited by FortyGuard.", status_code=resp.status,
                                payload=body, retry_after=retry_after,
                            )
                        if resp.status >= 500:
                            raise FortyGuardServerError(
                                f"FortyGuard server error ({resp.status}).",
                                status_code=resp.status, payload=body,
                            )

                        # Any other unexpected status — don't retry blindly.
                        raise FortyGuardError(
                            f"Unexpected status {resp.status}", status_code=resp.status, payload=body,
                        )

            except (FortyGuardAuthError, FortyGuardBadRequestError):
                raise  # never worth retrying

            except FortyGuardRateLimitError as e:
                last_error = e
                wait = e.retry_after or self._backoff_seconds(attempt)
                logger.warning("Rate limited (attempt %d/%d). Sleeping %.1fs.", attempt, self.config.max_retries, wait)
                await asyncio.sleep(wait)

            except (FortyGuardServerError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                wait = self._backoff_seconds(attempt)
                logger.warning(
                    "Request failed (%s), attempt %d/%d. Retrying in %.1fs.",
                    e, attempt, self.config.max_retries, wait,
                )
                if attempt < self.config.max_retries:
                    await asyncio.sleep(wait)

        assert last_error is not None
        if isinstance(last_error, FortyGuardError):
            raise last_error
        raise FortyGuardError(f"Request to {path} failed after {self.config.max_retries} attempts: {last_error}")

    def _backoff_seconds(self, attempt: int) -> float:
        return self.config.retry_backoff_base_seconds ** attempt

    # --------------------------------------------------------------------- #
    # Polling (Check Status) — shared by every async endpoint
    # --------------------------------------------------------------------- #

    async def _poll_until_complete(self, activity_id: str, *, endpoint_label: str) -> Dict[str, Any]:
        """
        Poll GET /status/{activity_id} until status reaches a terminal value.
        Bounded by config.poll_max_attempts * config.poll_interval_seconds.
        """
        for _ in range(self.config.poll_max_attempts):
            body = await self._request("GET", f"/status/{activity_id}")
            data = body.get("data", {})
            status = data.get("status")

            if status in _TERMINAL_SUCCESS_VALUES:
                return data.get("result", {})

            if status in _TERMINAL_FAILURE_VALUES:
                raise FortyGuardActivityFailedError(
                    f"{endpoint_label} activity failed.", activity_id=activity_id, payload=body,
                )

            # Processing / Pending / unknown-but-non-terminal -> keep polling
            await asyncio.sleep(self.config.poll_interval_seconds)

        raise FortyGuardTimeoutError(
            f"{endpoint_label} activity {activity_id} did not complete within "
            f"{self.config.poll_max_attempts * self.config.poll_interval_seconds:.0f}s.",
            activity_id=activity_id,
        )

    async def _submit_and_wait(
        self, path: str, payload: Dict[str, Any], *, endpoint_label: str
    ) -> Dict[str, Any]:
        submit_body = await self._request("POST", path, json_body=payload)
        activity_id = submit_body.get("data", {}).get("activity_id")
        if not activity_id:
            raise FortyGuardError(
                f"{endpoint_label} submission did not return an activity_id.", payload=submit_body,
            )
        logger.info("%s submitted (activity_id=%s). Polling for result...", endpoint_label, activity_id)
        return await self._poll_until_complete(activity_id, endpoint_label=endpoint_label)

    async def submit(self, path: str, payload: Dict[str, Any], *, endpoint_label: str) -> ActivityHandle:
        """
        Fire-and-return-handle variant, for callers (e.g. the LangGraph agent)
        that want to submit many jobs concurrently and poll them separately.
        """
        submit_body = await self._request("POST", path, json_body=payload)
        activity_id = submit_body.get("data", {}).get("activity_id")
        if not activity_id:
            raise FortyGuardError(f"{endpoint_label} submission did not return an activity_id.", payload=submit_body)
        return ActivityHandle(activity_id=activity_id, endpoint=endpoint_label)

    async def get_result(self, handle: ActivityHandle) -> Dict[str, Any]:
        """Poll a previously-submitted ActivityHandle to completion."""
        return await self._poll_until_complete(handle.activity_id, endpoint_label=handle.endpoint)

    # --------------------------------------------------------------------- #
    # 1. Create Heatmap
    # --------------------------------------------------------------------- #

    async def create_heatmap(
        self,
        *,
        polygon_aoi: Dict[str, Any],
        start_date: Union[str, date],
        filter_type: int,
        granularity: int = 100,
        end_date: Optional[Union[str, date]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        analytic_type: AnalyticType = "tcm",
        threshold: Optional[float] = None,
        direction: Direction = "above",
    ) -> Dict[str, Any]:
        """
        Generate a temperature heatmap over `polygon_aoi`.

        `filter_type`: 1=Single Hour, 2=Range of Hours, 3=Single Day,
                        4=Range of Days, 5=Single Month (unconfirmed fields).
        `analytic_type`: 'tcm' (°C snapshot, default), 'time_of_measure',
                          'exceedance', or 'persistence' (all three return hours).
        `threshold`/`direction` only apply to exceedance/persistence and are
        ignored (with a warning) for tcm / time_of_measure.

        Raises ValueError if polygon_aoi exceeds FortyGuard's ~130 km^2 heatmap limit.
        """
        if granularity not in (60, 80, 100):
            raise ValueError("granularity must be 60, 80, or 100 (meters)")

        area_km2 = _polygon_area_km2(polygon_aoi)
        if area_km2 > _MAX_HEATMAP_AREA_KM2:
            raise ValueError(
                f"polygon_aoi area (~{area_km2:.0f} km^2) exceeds FortyGuard's "
                f"heatmap limit of ~{_MAX_HEATMAP_AREA_KM2:.0f} km^2 (50 mi^2). "
                "Split the area into smaller requests or zoom in."
            )

        if analytic_type in ("tcm", "time_of_measure") and (threshold is not None):
            logger.warning(
                "threshold/direction are ignored by analytic_type=%r; FortyGuard will disregard them.",
                analytic_type,
            )

        payload: Dict[str, Any] = {
            "polygon_aoi": polygon_aoi,
            "date_time": _date_time_block(
                start_date=start_date, filter_type=filter_type,
                end_date=end_date, start_time=start_time, end_time=end_time,
            ),
            "granularity": granularity,
            "analytic_type": analytic_type,
        }
        if analytic_type in ("exceedance", "persistence"):
            payload["threshold"] = threshold if threshold is not None else 30.0
            payload["direction"] = direction

        return await self._submit_and_wait("/heatmap", payload, endpoint_label="Create Heatmap")

    @staticmethod
    def heatmap_tiles_to_geodataframe(result: Dict[str, Any]):
        """
        Convert `result['map_data']` (GeoJSON FeatureCollection) into a
        GeoDataFrame. Imports geopandas lazily so the base wrapper has no
        hard dependency on it for callers who only need the raw dict/stats.
        """
        import geopandas as gpd

        map_data = result.get("map_data")
        if not map_data:
            return gpd.GeoDataFrame()
        return gpd.GeoDataFrame.from_features(map_data.get("features", []))

    @staticmethod
    def heatmap_stats_to_dataframe(result: Dict[str, Any]) -> pd.DataFrame:
        """Flatten `result['stats_data'].Temperature_stats` into a one-row DataFrame."""
        stats = (result.get("stats_data") or {}).get("Temperature_stats", {})
        return pd.DataFrame([stats])

    # --------------------------------------------------------------------- #
    # 2. Satellite View Segmentation
    # --------------------------------------------------------------------- #

    async def satellite_segmentation(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: Union[str, date],
        filter_type: int,
        granularity: int = 100,
        end_date: Optional[Union[str, date]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Segment satellite imagery at a single point (building/road/vegetation
        class coverage). `filter_type` only supports 1-3 here (no Range of Days).
        """
        if filter_type == 4:
            raise ValueError("Satellite View Segmentation does not support filter_type=4 (Range of Days)")
        if granularity not in (60, 80, 100):
            raise ValueError("granularity must be 60, 80, or 100")

        payload = {
            "sat": {"latitude": latitude, "longitude": longitude},
            "date_time": _date_time_block(
                start_date=start_date, filter_type=filter_type,
                end_date=end_date, start_time=start_time, end_time=end_time,
            ),
            "granularity": granularity,
        }
        return await self._submit_and_wait("/satellite", payload, endpoint_label="Satellite View Segmentation")

    async def satellite_segmentation_grid(
        self,
        *,
        points: Sequence[tuple],  # [(lat, lon), ...]
        start_date: Union[str, date],
        filter_type: int,
        granularity: int = 100,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Run satellite_segmentation over multiple points concurrently (bounded
        by config.max_concurrent_requests via the internal semaphore).
        Use this to cover a polygon area, since the endpoint itself only
        accepts a single lat/lon per call.
        """
        tasks = [
            self.satellite_segmentation(
                latitude=lat, longitude=lon, start_date=start_date,
                filter_type=filter_type, granularity=granularity, **kwargs,
            )
            for lat, lon in points
        ]
        return await asyncio.gather(*tasks)

    # --------------------------------------------------------------------- #
    # 3. Street View Segmentation
    # --------------------------------------------------------------------- #

    async def street_segmentation(
        self,
        *,
        latitude: float,
        longitude: float,
        vertical_angle: float = 0.0,
        horizontal_angle: float = 0.0,
        back_view: bool = False,
    ) -> Dict[str, Any]:
        """Segment ground-level street-view imagery at a point (no date/time — imagery is dated by capture)."""
        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "vertical_angle": vertical_angle,
            "horizontal_angle": horizontal_angle,
            "back_view": back_view,
        }
        return await self._submit_and_wait("/streetview", payload, endpoint_label="Street View Segmentation")

    # --------------------------------------------------------------------- #
    # 4. Heat Intelligence (returns a PDF via temporary download_link)
    # --------------------------------------------------------------------- #

    async def heat_intelligence(
        self,
        *,
        latitude: float,
        longitude: float,
        temperature: float,
        date_: Union[str, date],
        analysis: Sequence[HeatIntelAnalysis] = ("environmental",),
    ) -> Dict[str, Any]:
        """
        Request a Heat Intelligence PDF report. Returns the result dict
        containing `download_link` (a TEMPORARY signed URL). This wrapper
        does not log the link — fetch it immediately via `download_heat_intelligence_pdf`.
        """
        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "temperature": temperature,
            "date": date_.isoformat() if isinstance(date_, date) else date_,
            "analysis": list(analysis),
        }
        return await self._submit_and_wait("/heat_intelligence", payload, endpoint_label="Heat Intelligence")

    async def download_heat_intelligence_pdf(self, result: Dict[str, Any], *, output_path: str) -> str:
        """
        Fetch the PDF from result['download_link'] and save it to `output_path`.
        Call this immediately after `heat_intelligence()` — the link is temporary.
        """
        download_link = result.get("download_link")
        if not download_link:
            raise FortyGuardError("Heat Intelligence result has no download_link.")

        session = self._require_session()
        async with session.get(download_link) as resp:
            if resp.status != 200:
                raise FortyGuardError(f"Failed to download Heat Intelligence PDF (status {resp.status}).")
            content = await resp.read()

        with open(output_path, "wb") as f:
            f.write(content)
        return output_path

    # --------------------------------------------------------------------- #
    # 5. Environmental Parameters
    # --------------------------------------------------------------------- #

    async def environmental_parameters(
        self,
        *,
        latitude: float,
        longitude: float,
        temperature: float,
        start_date: Union[str, date],
        filter_type: int,
        end_date: Optional[Union[str, date]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        analysis: Optional[Sequence[str]] = None,
        plan_limits_to_3: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch environmental parameters (heat index, AQI, solar irradiance, etc).

        `analysis`: omit for all parameters (Premium) or pass a subset.
        `plan_limits_to_3`: set True if your key is on a Basic/limited plan —
        raises early with a clear error instead of a confusing 400 from the API.
        Missing values come back as JSON `null` (not 0) — treat them as "no data".
        """
        if filter_type == 4:
            raise ValueError("Environmental Parameters does not support filter_type=4 (Range of Days)")
        if plan_limits_to_3 and analysis and len(analysis) > 3:
            raise ValueError(
                f"{len(analysis)} parameters requested but this plan is limited to 3 per request."
            )

        payload: Dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "temperature": temperature,
            "date_time": _date_time_block(
                start_date=start_date, filter_type=filter_type,
                end_date=end_date, start_time=start_time, end_time=end_time,
            ),
        }
        if analysis:
            payload["analysis"] = list(analysis)

        return await self._submit_and_wait("/env_params", payload, endpoint_label="Environmental Parameters")

    @staticmethod
    def environmental_parameters_to_dataframe(result: Dict[str, Any]) -> pd.DataFrame:
        """
        Flatten `result['locations'][0]['parameters']` (dict of name -> [values])
        into a tidy DataFrame indexed by the response's timestamps, treating
        JSON null correctly as NaN (never as 0).
        """
        locations = result.get("locations") or []
        if not locations:
            return pd.DataFrame()

        loc = locations[0]
        params = loc.get("parameters", {})
        timestamps = (result.get("metadata") or {}).get("timestamps", [])

        df = pd.DataFrame(params)
        if timestamps and len(timestamps) == len(df):
            df.index = pd.to_datetime(timestamps)
            df.index.name = "timestamp"
        df = df.where(pd.notnull(df), None)  # keep nulls explicit, never coerce to 0
        df.attrs["latitude"] = loc.get("lat")
        df.attrs["longitude"] = loc.get("lon")
        df.attrs["elevation"] = loc.get("elevation")
        return df

    # --------------------------------------------------------------------- #
    # 6. Check API Credits Usage
    # --------------------------------------------------------------------- #

    async def check_credits_usage(self) -> Dict[str, Any]:
        """
        Returns current plan / credit usage.

        Confirmed via the Participant Handbook (§7.5): POST /v1/system/fetch-api-key-usage
        """
        return await self._request("POST", "/system/fetch-api-key-usage")

    # --------------------------------------------------------------------- #
    # 7. Check Status (exposed directly for callers managing their own handles)
    # --------------------------------------------------------------------- #

    async def check_status(self, activity_id: str) -> Dict[str, Any]:
        """Raw single status check (no polling loop) — mainly for debugging/UI progress bars."""
        body = await self._request("GET", f"/status/{activity_id}")
        return body.get("data", {})


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #

def _safe_json(text: str) -> Any:
    import json
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {"raw": text}


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None