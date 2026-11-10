"""
FILE: farm_twin/domain/water_state.py
PURPOSE: WaterState at plot AND property level (supply side + storage + fluxes).

IMPLEMENT: class WaterSource(kind in {GROUNDWATER_WELL, RAINWATER_TANK, CANAL, TANKER, FARM_POND, MUNICIPAL}, capacity_m3,
        yield_m3_per_day|None, seasonal_availability: monthly array(12) of m3, quality: ec_dSm, sar, cost_inr_per_m3,
        pumping_kwh_per_m3 (from head/efficiency), reliability: Uncertainty)
    class StorageAsset(volume_m3, level_m3, evap_loss_model, seepage_loss_frac_per_day, catchment_area_m2, runoff_coefficient)
    class WaterState: sources, storages, plot_irrigation_demand_mm (per plot/day), water_balance_ledger (daily list of
        precip, irrigation, runoff, drainage, ET, dStorage, residual) used by the mass-balance checker.
    method: rooftop_harvest_m3(roof_area_m2, rain_mm, first_flush_mm=1.0, coeff=0.8)  -> max(0, rain_mm-first_flush_mm)*roof_area*coeff/1000
TESTS: tank mass balance over a synthetic year closes within 0.1%.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, model_validator


class WaterSourceKind(str, Enum):
    GROUNDWATER_WELL = "GROUNDWATER_WELL"
    RAINWATER_TANK = "RAINWATER_TANK"
    CANAL = "CANAL"
    TANKER = "TANKER"
    FARM_POND = "FARM_POND"
    MUNICIPAL = "MUNICIPAL"


class WaterSource(BaseModel):
    kind: WaterSourceKind
    capacity_m3: float | None = None
    yield_m3_per_day: float | None = None
    seasonal_availability_m3: list[float] = Field(default_factory=lambda: [0.0] * 12)
    quality: dict[str, float | None] = Field(default_factory=dict)
    cost_inr_per_m3: float | None = None
    pumping_kwh_per_m3: float | None = None
    reliability: dict | None = None


class StorageAsset(BaseModel):
    volume_m3: float
    level_m3: float = 0
    evap_loss_model: dict = Field(default_factory=dict)
    seepage_loss_frac_per_day: float = 0
    catchment_area_m2: float = 0
    runoff_coefficient: float = 0.8

    @model_validator(mode="after")
    def valid_storage(self) -> "StorageAsset":
        if not 0 <= self.level_m3 <= self.volume_m3 or not 0 <= self.seepage_loss_frac_per_day <= 1:
            raise ValueError("storage level or seepage fraction outside physical limits")
        return self


class WaterState(BaseModel):
    sources: list[WaterSource] = Field(default_factory=list)
    storages: list[StorageAsset] = Field(default_factory=list)
    plot_irrigation_demand_mm: dict[str, float] = Field(default_factory=dict)
    water_balance_ledger: list[dict[str, float]] = Field(default_factory=list)

    @staticmethod
    def rooftop_harvest_m3(
        roof_area_m2: float, rain_mm: float, first_flush_mm: float = 1.0, coeff: float = 0.8
    ) -> float:
        if roof_area_m2 < 0 or rain_mm < 0 or not 0 <= coeff <= 1:
            raise ValueError("roof area, rainfall, and coefficient must be physically valid")
        return max(0.0, rain_mm - first_flush_mm) * roof_area_m2 * coeff / 1000.0
