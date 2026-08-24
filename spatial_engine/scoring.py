"""
Heat Risk scoring logic — pure functions, no network calls.

The Heat Risk Index (0-100) combines three signals for a location:
  1. Temperature severity   — how hot relative to the AOI's own range
  2. Impervious surface     — building + road coverage (traps/re-radiates heat)
  3. Vegetation deficit     — lack of tree canopy (no shade, no evapotranspiration cooling)

Keeping this in a separate module (no aiohttp/FortyGuardClient imports) means
it can be unit-tested with plain numbers and reused anywhere — the Streamlit
UI, the LangGraph tools, or a notebook — without spinning up API calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class RiskWeights:
    """Relative importance of each factor. Must sum to 1.0."""
    temperature: float = 0.5
    impervious_surface: float = 0.25
    vegetation_deficit: float = 0.25

    def __post_init__(self):
        total = self.temperature + self.impervious_surface + self.vegetation_deficit
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"RiskWeights must sum to 1.0, got {total}")


DEFAULT_WEIGHTS = RiskWeights()

# Segmentation class names observed from FortyGuard's satellite/street
# segmentation `segments` dict. Class sets differ slightly between the two
# endpoints (e.g. street view adds "sky", "sidewalk", "fountain"), so we
# match by keyword rather than an exact fixed list.
_IMPERVIOUS_KEYWORDS = ("building", "road", "route", "sidewalk", "floor", "pavement", "asphalt")
_VEGETATION_KEYWORDS = ("tree", "grass", "vegetation", "canopy")


@dataclass
class RiskBreakdown:
    """Explainable output — the score plus what drove it, for the agent/UI to narrate."""
    score: float
    category: str
    temperature_c: float
    temperature_contribution: float
    impervious_pct: float
    impervious_contribution: float
    vegetation_pct: float
    vegetation_deficit_contribution: float
    notes: Optional[str] = None

    def explain(self) -> str:
        """Human-readable one-liner, e.g. for a Triage Report or chat response."""
        veg_phrase = (
            f"only {self.vegetation_pct:.0f}% tree canopy"
            if self.vegetation_pct < 40
            else f"a healthy {self.vegetation_pct:.0f}% tree canopy"
        )
        return (
            f"{self.category} risk ({self.score:.0f}/100): "
            f"{self.temperature_c:.1f}°C "
            f"(+{self.temperature_contribution:.0f} pts), "
            f"{self.impervious_pct:.0f}% impervious surface "
            f"(+{self.impervious_contribution:.0f} pts), "
            f"{veg_phrase} "
            f"(+{self.vegetation_deficit_contribution:.0f} pts)."
        )


def extract_impervious_pct(segments: Dict[str, float]) -> float:
    """Sum segment classes that count as heat-trapping impervious surface."""
    return sum(v for k, v in segments.items() if any(kw in k.lower() for kw in _IMPERVIOUS_KEYWORDS))


def extract_vegetation_pct(segments: Dict[str, float]) -> float:
    """Sum segment classes that count as cooling vegetation."""
    return sum(v for k, v in segments.items() if any(kw in k.lower() for kw in _VEGETATION_KEYWORDS))


def normalize_temperature(
    temp_c: float, *, aoi_min_c: float, aoi_max_c: float
) -> float:
    """
    Map a temperature into a 0-100 severity score, relative to the AOI's own
    min/max (so the score reflects *local* hot spots, not an arbitrary global
    scale). Falls back to 50 (neutral) if the AOI has no spread at all.
    """
    spread = aoi_max_c - aoi_min_c
    if spread <= 0:
        return 50.0
    return max(0.0, min(100.0, (temp_c - aoi_min_c) / spread * 100.0))


def categorize(score: float) -> str:
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Moderate"
    return "Low"


def compute_heat_risk(
    *,
    temperature_c: float,
    aoi_min_c: float,
    aoi_max_c: float,
    segments: Dict[str, float],
    weights: RiskWeights = DEFAULT_WEIGHTS,
) -> RiskBreakdown:
    """
    Compute a single location's Heat Risk Index from its temperature and
    satellite/street segmentation class coverage.

    `segments` is the raw `segments` dict returned by satellite_segmentation()
    or street_segmentation() (e.g. {'tree': 37.83, 'building': 0.64, ...}).
    """
    impervious_pct = extract_impervious_pct(segments)
    vegetation_pct = extract_vegetation_pct(segments)
    vegetation_deficit_pct = max(0.0, 100.0 - vegetation_pct)

    temp_score = normalize_temperature(temperature_c, aoi_min_c=aoi_min_c, aoi_max_c=aoi_max_c)

    temp_contribution = temp_score * weights.temperature
    impervious_contribution = impervious_pct * weights.impervious_surface
    vegetation_contribution = vegetation_deficit_pct * weights.vegetation_deficit

    score = temp_contribution + impervious_contribution + vegetation_contribution
    score = max(0.0, min(100.0, score))

    return RiskBreakdown(
        score=score,
        category=categorize(score),
        temperature_c=temperature_c,
        temperature_contribution=temp_contribution,
        impervious_pct=impervious_pct,
        impervious_contribution=impervious_contribution,
        vegetation_pct=vegetation_pct,
        vegetation_deficit_contribution=vegetation_contribution,
    )