"""
FILE: farm_twin/domain/infrastructure_state.py
PURPOSE: Capital assets other than PV: borewell/pump, drip network, tanks, fences, sheds, soil-moisture sensors, weather station.

IMPLEMENT: class InfraAsset(id, kind, plot_id|None, capex_inr, install_date, life_years, salvage_frac, opex_inr_per_year, capacity {unit,value},
           status {EXISTING, PLANNED, PROPOSED}), class InfraState(assets, maintenance_log).
           Irrigation-specific: IrrigationSystem(method {SURFACE, DRIP, SPRINKLER, MANUAL}, application_efficiency 0-1, wetted_surface_fraction 0-1,
           pump kW, flow_m3_h, energy_kwh_per_m3).  application_efficiency feeds directly into the crop-water solver (irrigation applied = net/eff).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class AssetStatus(str, Enum):
    EXISTING = "EXISTING"
    PLANNED = "PLANNED"
    PROPOSED = "PROPOSED"


class IrrigationMethod(str, Enum):
    SURFACE = "SURFACE"
    DRIP = "DRIP"
    SPRINKLER = "SPRINKLER"
    MANUAL = "MANUAL"


class InfraAsset(BaseModel):
    id: str
    kind: str
    plot_id: str | None = None
    capex_inr: float = 0
    install_date: date | None = None
    life_years: float | None = None
    salvage_frac: float = 0
    opex_inr_per_year: float = 0
    capacity: dict[str, float | str] = Field(default_factory=dict)
    status: AssetStatus = AssetStatus.PROPOSED


class IrrigationSystem(BaseModel):
    method: IrrigationMethod
    application_efficiency: float
    wetted_surface_fraction: float
    pump_kw: float | None = None
    flow_m3_h: float | None = None
    energy_kwh_per_m3: float | None = None

    @model_validator(mode="after")
    def ranges(self) -> "IrrigationSystem":
        if not 0 < self.application_efficiency <= 1 or not 0 <= self.wetted_surface_fraction <= 1:
            raise ValueError("irrigation efficiency and wetted fraction must be in [0,1] (efficiency > 0)")
        return self


class InfraState(BaseModel):
    assets: list[InfraAsset] = Field(default_factory=list)
    maintenance_log: list[dict] = Field(default_factory=list)
    irrigation_system: IrrigationSystem | None = None
