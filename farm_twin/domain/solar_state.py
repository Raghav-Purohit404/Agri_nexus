"""
FILE: farm_twin/domain/solar_state.py
PURPOSE: SolarState: description of PV assets and their running state.

IMPLEMENT: class PVConfig: kind {GROUND_FIXED, GROUND_TRACKER_1AXIS, ELEVATED_AGRIVOLTAIC_FIXED, VERTICAL_BIFACIAL, ROOFTOP},
        kWp, module params (pdc0_W, gamma_pdc_per_C, bifaciality, transmittance for semi-transparent), tilt_deg, azimuth_deg (180=south),
        row_pitch_m, clearance_height_m (lowest panel edge), collector_width_m (slant), gcr, n_rows, inverter (pdc0, eta_nom), losses (soiling, mismatch, wiring ...),
        degradation_pct_per_year, albedo, mounting_temp_model {open_rack, close_mount}, capex_inr, opex_inr_per_year
    class SolarState: configs by plot, hourly_generation series (MODEL_PREDICTED), soiling_state (cumulative dust loss; Rajasthan: significant), degradation_age_years.
TESTS: GCR == collector_width_slant / pitch for fixed-tilt rows (GCR uses the SLANT width; the horizontal footprint ratio is collector_width_slant*cos(tilt)/pitch and must be exposed separately as `footprint_ratio`).
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, model_validator


class PVKind(str, Enum):
    GROUND_FIXED = "GROUND_FIXED"
    GROUND_TRACKER_1AXIS = "GROUND_TRACKER_1AXIS"
    ELEVATED_AGRIVOLTAIC_FIXED = "ELEVATED_AGRIVOLTAIC_FIXED"
    VERTICAL_BIFACIAL = "VERTICAL_BIFACIAL"
    ROOFTOP = "ROOFTOP"


class PVConfig(BaseModel):
    kind: PVKind
    kWp: float
    pdc0_W: float | None = None
    gamma_pdc_per_C: float | None = None
    bifaciality: float | None = None
    transmittance: float = 0.0
    tilt_deg: float
    azimuth_deg: float = 180
    row_pitch_m: float | None = None
    clearance_height_m: float | None = None
    collector_width_m: float | None = None
    gcr: float | None = None
    n_rows: int | None = None
    inverter: dict[str, float] = Field(default_factory=dict)
    losses: dict[str, float] = Field(default_factory=dict)
    degradation_pct_per_year: float = 0
    albedo: float = 0.2
    mounting_temp_model: str = "open_rack"
    capex_inr: float | None = None
    opex_inr_per_year: float | None = None

    @model_validator(mode="after")
    def basic_validity(self) -> "PVConfig":
        if self.kWp <= 0 or not 0 <= self.transmittance <= 1 or not 0 <= self.albedo <= 1:
            raise ValueError("invalid PV size, transmittance, or albedo")
        if self.row_pitch_m and self.collector_width_m and self.gcr is not None:
            expected = self.collector_width_m / self.row_pitch_m
            if abs(expected - self.gcr) > 1e-6:
                raise ValueError("fixed-row GCR must use slant collector width / pitch")
        return self


class SolarState(BaseModel):
    configs: dict[str, PVConfig] = Field(default_factory=dict)
    hourly_generation: list[dict] = Field(default_factory=list)
    soiling_state: float = 0
    degradation_age_years: float = 0
