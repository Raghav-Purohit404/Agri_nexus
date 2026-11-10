"""
FILE: farm_twin/domain/crop_state.py
PURPOSE: CropState for one plot-season (the state vector of the crop simulator) + crop history.

IMPLEMENT: class CropState:
    crop_id, variety, planting_date, status {FALLOW, PLANTED, EMERGED, FLOWERING, YIELD_FORMATION, SENESCENCE, MATURE, HARVESTED, DEAD}
    dap (days after planting), gdd_cum, delayed_calendar_days, delayed_gdd (stress-induced phenology delay)
    canopy_cover (CC, fraction 0-1), cc_nostress, ccx_act, ccx_w, cc_prev, t_early_senescence_days, premature_senescence flag
    root_depth_m, root_cor (r_cor), biomass_t_ha, biomass_nostress_t_ha, harvest_index_ref, harvest_index_adj,
    f_pre, f_pol, f_post (HI adjustment factors), yield_formation flag, pct_lag_phase
    transpiration_cum_mm, evaporation_cum_mm, irrigation_cum_mm, drought stress counters (days of Ksw<1 by type)
    n_uptake_cum_kg_ha, n_stress_factor, salinity_stress_factor
  class CropHistoryRecord: plot_id, season, crop, variety, planting_date, harvest_date, yield_t_ha: Quantified, irrigation_mm, fertiliser applications, notes.
TESTS: serialisation round trip; CropState default for FALLOW has canopy_cover == 0.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class CropStatus(str, Enum):
    FALLOW = "FALLOW"
    PLANTED = "PLANTED"
    EMERGED = "EMERGED"
    FLOWERING = "FLOWERING"
    YIELD_FORMATION = "YIELD_FORMATION"
    SENESCENCE = "SENESCENCE"
    MATURE = "MATURE"
    HARVESTED = "HARVESTED"
    DEAD = "DEAD"


class CropState(BaseModel):
    crop_id: str | None = None
    variety: str | None = None
    planting_date: date | None = None
    status: CropStatus = CropStatus.FALLOW
    dap: int = 0
    gdd_cum: float = 0.0
    delayed_calendar_days: float = 0.0
    delayed_gdd: float = 0.0
    canopy_cover: float = 0.0
    cc_nostress: float = 0.0
    ccx_act: float = 0.0
    ccx_w: float = 0.0
    cc_prev: float = 0.0
    t_early_senescence_days: float = 0.0
    premature_senescence: bool = False
    root_depth_m: float = 0.0
    root_cor: float = 1.0
    biomass_t_ha: float = 0.0
    biomass_nostress_t_ha: float = 0.0
    harvest_index_ref: float = 0.0
    harvest_index_adj: float = 0.0
    f_pre: float = 1.0
    f_pol: float = 1.0
    f_post: float = 1.0
    yield_formation: bool = False
    pct_lag_phase: float = 0.0
    transpiration_cum_mm: float = 0.0
    evaporation_cum_mm: float = 0.0
    irrigation_cum_mm: float = 0.0
    drought_stress_days: dict[str, int] = Field(default_factory=dict)
    n_uptake_cum_kg_ha: float = 0.0
    n_stress_factor: float = 1.0
    salinity_stress_factor: float = 1.0


class CropHistoryRecord(BaseModel):
    plot_id: str
    season: str
    crop: str
    variety: str | None = None
    planting_date: date
    harvest_date: date | None = None
    yield_t_ha: object | None = None
    irrigation_mm: float | None = None
    fertiliser_applications: list[dict] = Field(default_factory=list)
    notes: str | None = None
