"""
FILE: farm_twin/models/crop/aquacrop_native.py
PURPOSE: Level-1 crop engine ("AquaCrop-equivalent", water-driven). The orchestrator that runs one plot-season day by day.
IT MUST BE AN ORIGINAL IMPLEMENTATION written from this specification (modules: phenology_roots, canopy, stress, transpiration_biomass_hi, soil/water_balance), vectorised over (scenario) axis with numba or numpy.

DAILY ORDER OF OPERATIONS [VERIFIED against the reference daily loop]:
   day = weather row (Tmax,Tmin,P,ET0,date)
   1  if date outside [planting, maturity]: only soil water balance with no crop (fallow evaporation)
   2  GDD(day); advance crop calendar (t_adj, stage)
   3  growth stage (emergence -> ... ) and `crop_alive` flag
   4  pre-irrigation-day stress/depletion check: compute TAW, Dr at start of day
   5  root development (Zr)
   6  irrigation decision (policy in interventions) -> gross applied depth
   7  water balance part 1: drainage, runoff & infiltration (CN), irrigation, infiltration to layers
   8  capillary rise / groundwater (if enabled)
   9  stress coefficients (water: exp, sto, sen, pol; aeration; temperature; salinity; nitrogen)  [stress.py]
  10  canopy development (CC) using Ks_exp/Ks_sen [canopy.py]
  11  soil evaporation (two-stage with CC shading) [water_balance]
  12  transpiration demand & actual with root extraction [transpiration_biomass_hi]
  13  biomass accumulation (dB) with all stress multipliers [transpiration_biomass_hi]
  14  harvest index / yield formation [transpiration_biomass_hi]
  15  update CropState, ledger, check mass balance, emit DailyOutput(row)
  16  maturity / death check -> season summary (yield, water use, WUE, irrigation, stress days by type)
INPUTS: plot soil layers (pedotransfer or measured), crop parameter set (library + hierarchy overrides), weather (Tmax,Tmin,P,ET0 [+Rs, u2, RH for ET0]), planting date, irrigation policy, fertility inputs, optional microclimate factors.
OUTPUTS: DailyOutput DataFrame: date, dap, gdd_cum, stage, cc, zr, theta_layers, dr_mm, taw_mm, ks_*, es_mm, tr_mm, tr_pot_mm, runoff_mm, deep_perc_mm, irr_mm, biomass_t_ha, hi_adj, yield_t_ha, n_stress, sal_stress + SeasonSummary.
SCENARIO VECTORISATION: simulate N weather scenarios simultaneously (arrays shape [N]) - target performance: 1 plot x 1 season x 100 scenarios < 1 s with numba.
VALIDATION: golden fixtures from tests/golden/ (AquaCrop Tunis wheat: rainfed yields 8.930, 8.393, 9.139, 8.776, 8.710, 8.913 t/ha for seasons 1980-85 with Sandy Loam, planting 15 Oct, FC initial water; irrigated SMT=70 % in all four stages: seasonal irrigation 36.0, 85.9, 62.2, 111.0, 50.0, 36.9 mm). Acceptance: yield +/-3 %, irrigation +/-5 mm, daily CC +/-0.01.
EXTENSIBILITY: Crop-specific modules plug via CropTraits flags: determinate/indeterminate, CropType {leafy, root, fruit/grain}, perennial (unsupported L1), legume N fixation hook (supply term in nutrients.py), C4 flag (affects WP normalisation and CO2 response).
KNOWN LIMITS TO PRINT IN EVERY REPORT: water-driven growth (no explicit light/N/P/K dynamics unless modules attached), no pest/disease, no lodging, no waterlogging beyond aeration factor, no salinity feedback on soil unless salinity.py is attached.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from farm_twin.models.crop.canopy import cc_growth, cc_curve
from farm_twin.models.crop.phenology_roots import growing_degree_days, potential_root_depth, actual_root_depth, stage_of
from farm_twin.models.crop.stress import water_stress
from farm_twin.models.crop.transpiration_biomass_hi import (
    find_higc,
    harvest_index_reference,
    transpiration_potential,
    biomass_increment,
    yield_t_ha,
)
from farm_twin.models.soil.water_balance import DailyForcing, LayeredWaterBalance, WaterColumn, root_zone_water


class SeasonSummary(BaseModel):
    crop_id: str
    season: str
    dry_yield_t_ha: float
    fresh_yield_t_ha: float
    seasonal_irrigation_mm: float
    seasonal_transpiration_mm: float
    biomass_t_ha: float
    fidelity_status: str = "IMPLEMENTED_NOT_GOLDEN_VALIDATED"
    limitations: list[str] = Field(
        default_factory=lambda: ["salinity and nutrient coupling not active", "wheat fixture not reproduced"]
    )


class CropRunResult(BaseModel):
    daily: list[dict[str, Any]]
    summary: SeasonSummary


def run_season(
    weather: pd.DataFrame,
    crop_parameters: dict[str, Any],
    initial_water: WaterColumn,
    planting_date: date,
    *,
    irrigation_policy: dict[str, Any] | None = None,
    area_m2: float = 1.0,
    elevation_m: float = 0.0,
    water_balance: LayeredWaterBalance | None = None,
) -> CropRunResult:
    """Run the L1 daily crop/water loop from explicit parameters and initial soil water.

    This original engine is a specified, not yet golden-validated implementation; it does not
    fabricate absent crop parameters or calibrated fertility/salt response values.
    """
    p = crop_parameters.get("parameters", crop_parameters)
    policy = irrigation_policy or {"mode": "RAINFED"}
    if str(p.get("cycle", "annual")).lower() == "perennial":
        raise NotImplementedError("perennial/regrowth crops are outside L1")
    required = ["tmax_c", "tmin_c", "rain_mm", "et0_mm"]
    if not set(required).issubset(weather.columns):
        raise ValueError(f"weather requires columns {required}")
    data = weather.copy()
    if "date" not in data:
        data["date"] = data.index
    data["date"] = pd.to_datetime(data["date"]).dt.date
    data = data[data.date >= planting_date].reset_index(drop=True)
    if data.empty:
        raise ValueError("weather has no records on or after planting")

    def param(key, default=None):
        return p.get(key, default)

    ccx = float(param("CCx", 0.96))
    cc0 = float(param("cc0", float(param("PlantPop", 0)) * float(param("SeedSize", 0)) * 1e-8))
    cgc = float(param("CGC", param("CGC_CD", 0.04901)))
    cdc = abs(float(param("CDC", param("CDC_CD", 0.07179))))
    emergence = float(param("Emergence", param("EmergenceCD", 13)))
    max_rooting = float(param("MaxRooting", param("MaxRootingCD", 93)))
    senescence = float(param("Senescence", param("SenescenceCD", 158)))
    maturity = float(param("Maturity", param("MaturityCD", 197)))
    hi_start = float(param("HIstart", param("HIstartCD", 127)))
    flowering = float(param("Flowering", param("FloweringCD", hi_start - 15)))
    calendar_type = int(param("CalendarType", 1))
    gdd_method = int(param("GDDmethod", 3))
    zmin = float(param("Zmin", 0.3))
    zmax = float(param("Zmax", 1.5))
    pct_zmin = float(param("PctZmin", 40))
    fshape_r = float(param("fshape_r", 1.5))
    hi0 = float(param("HI0", 0.48))
    yld_days = int(param("YldForm", param("YldFormCD", 67)))
    higc = find_higc(hi0, max(1, yld_days))
    wp = float(param("WP", 15))
    model = water_balance or LayeredWaterBalance()
    column = initial_water.model_copy(deep=True)
    cc = biomass = biomass_nostress = irrigation_sum = tr_sum = 0.0
    root_depth = zmin
    previous_potential = zmin * pct_zmin / 100
    daily = []
    season_cap = float(policy.get("season_cap_mm", float("inf")))
    max_depth = float(policy.get("max_depth_mm", float("inf")))
    gdd_cumulative = 0.0
    for index, row in data.iterrows():
        dap = index + 1
        tmax = float(row.tmax_c)
        tmin = float(row.tmin_c)
        et0 = max(0, float(row.et0_mm))
        rain = max(0, float(row.rain_mm))
        gdd = growing_degree_days(tmax, tmin, float(param("Tbase", 0)), float(param("Tupp", 26)), gdd_method)
        gdd_cumulative += gdd
        time_adj = float(dap) if calendar_type == 1 else gdd_cumulative
        stage = stage_of(time_adj, emergence, flowering, hi_start, senescence, maturity)
        potential = potential_root_depth(time_adj, zmin, zmax, pct_zmin, emergence, max_rooting, fshape_r)
        entered = next(
            (layer for layer in column.layers if layer.bottom_m >= max(root_depth, potential)), column.layers[-1]
        )
        root_depth = actual_root_depth(
            root_depth,
            potential,
            previous_potential,
            entered.theta,
            entered.theta_wp,
            entered.theta_fc,
            column.layers[-1].bottom_m,
        )
        rz = root_zone_water(column.layers, root_depth)
        dr_frac = min(1, max(0, rz.depletion_mm / max(rz.taw_mm, 1e-9)))
        ks_exp = water_stress(
            dr_frac, float(param("p_up1", 0.2)), float(param("p_lo1", 0.65)), float(param("fshape_w1", 5))
        )
        ks_sto = water_stress(
            dr_frac, float(param("p_up2", 0.65)), float(param("p_lo2", 1)), float(param("fshape_w2", 2.5))
        )
        prev_cc = cc
        if time_adj < senescence:
            cc = cc_growth(time_adj - emergence, cc0, ccx, cgc, cc, ks_exp)
        else:
            cc = cc_curve(time_adj, cc0, ccx, cgc, senescence, cdc, ccx)
        tr_pot = transpiration_potential(float(param("Kcb", 1.1)), cc, et0)
        gross = 0.0
        mode = policy.get("mode", "RAINFED")
        if mode == "FIXED_SCHEDULE":
            gross = float(policy.get("schedule_mm", {}).get(str(row.date), 0))
        elif (
            mode == "SOIL_MOISTURE_THRESHOLD"
            and rz.taw_mm > 0
            and dr_frac > 1 - float(policy.get("smt_pct_taw", 70)) / 100
        ):
            gross = min(max_depth, max(0, rz.depletion_mm)) / float(policy.get("application_efficiency", 1))
        gross = min(gross, max(0, season_cap - irrigation_sum))
        forcing = DailyForcing(
            rain_mm=rain,
            et0_mm=et0,
            irrigation_gross_mm=gross,
            irrigation_efficiency=float(policy.get("application_efficiency", 1)),
            crop_transpiration_demand_mm=tr_pot * ks_sto,
            canopy_cover=cc,
            curve_number=float(policy.get("curve_number", 75)),
        )
        column, flux = model.step(column, forcing)
        irrigation_sum += flux.irrigation_net_mm
        tr_sum += flux.transpiration_mm
        db = biomass_increment(wp, flux.transpiration_mm, et0)
        biomass += db
        biomass_nostress += biomass_increment(wp, tr_pot, et0)
        hi_t = max(0, time_adj - hi_start)
        hi = harvest_index_reference(hi_t, hi0, higc)
        product_moisture = float(param("FC", 0.12))
        if product_moisture > 1:
            product_moisture /= 100
        dry, fresh = yield_t_ha(biomass, hi, product_moisture)
        daily.append(
            {
                "date": row.date,
                "dap": dap,
                "gdd": gdd,
                "stage": stage.value,
                "cc": cc,
                "cc_previous": prev_cc,
                "zr_m": root_depth,
                "dr_mm": rz.depletion_mm,
                "taw_mm": rz.taw_mm,
                "ks_exp": ks_exp,
                "ks_sto": ks_sto,
                "es_mm": flux.evaporation_mm,
                "tr_mm": flux.transpiration_mm,
                "tr_pot_mm": tr_pot,
                "runoff_mm": flux.runoff_mm,
                "deep_perc_mm": flux.deep_percolation_mm,
                "irr_mm": flux.irrigation_net_mm,
                "biomass_t_ha": biomass,
                "biomass_nostress_t_ha": biomass_nostress,
                "hi_ref": hi,
                "yield_dry_t_ha": dry,
                "yield_fresh_t_ha": fresh,
                "n_stress": None,
                "sal_stress": None,
                "quality_flags": ["fertility_unavailable", "salinity_unavailable"],
            }
        )
        if time_adj >= maturity or (cc < 0.02 and time_adj >= senescence):
            break
        previous_potential = potential
    last = daily[-1]
    summary = SeasonSummary(
        crop_id=str(param("Name", "unknown")),
        season=str(planting_date.year),
        dry_yield_t_ha=last["yield_dry_t_ha"],
        fresh_yield_t_ha=last["yield_fresh_t_ha"],
        seasonal_irrigation_mm=irrigation_sum,
        seasonal_transpiration_mm=tr_sum,
        biomass_t_ha=biomass,
    )
    return CropRunResult(daily=daily, summary=summary)
