"""
FILE: farm_twin/models/soil/water_balance.py
PURPOSE: Daily multi-layer soil-water balance (the physical core shared by crop, salinity and nutrient models). Level 1 = layered tipping-bucket with the processes below, executed in this EXACT order each day (order matters for mass balance):

  1. groundwater table check (adjust theta_fc in saturated zone) [if water table present]
  2. root development (from the crop model; Zr)
  3. drainage (redistribution below field capacity)
  4. surface runoff + infiltration partitioning (curve number)
  5. irrigation (applied depth, efficiency, wetted-surface fraction)
  6. infiltration into layers with Ksat cap, surface storage / ponding
  7. capillary rise from water table
  8. soil evaporation (two-stage, REW)
  9. crop transpiration extraction (root-weighted sink, stress-limited)  [needs crop model's Tr demand]
 10. groundwater inflow
 -> compute stress coefficients for next day; write ledger; assert mass balance.

EQUATIONS:
 (a) Drainage per layer i (tau_i from pedotransfer, theta_fcAdj = FC unless water table):
       if theta <= theta_fcAdj: dTh = 0
       elif theta >= theta_sat: dTh = tau*(theta_sat - theta_fc)
       else: dTh = tau*(theta_sat - theta_fc)*(exp(theta - theta_fc) - 1)/(exp(theta_sat - theta_fc) - 1)
       dTh limited so theta - dTh >= theta_fcAdj; flux out = dTh*dz*1000 [mm]
       Process layers top->bottom: the drained water from layer i enters layer i+1; layer i+1 can accept at most up to theta_sat (excess is held back in layer i);
       the flux between layers is capped by Ksat of the receiving layer; the bottom layer flux is DEEP PERCOLATION (a loss; count in ledger).
       (Implement the full "drainability" logic: if the cumulative incoming flux exceeds what the layer can drain, the layer is filled toward saturation and any remainder is pushed back up as reduced upstream drainage. Reproduce with unit tests on a 3-layer column.)
 (b) Runoff via SCS curve number:
       CN adjusted for antecedent moisture: CN_dry = 1.4*10^-14 + 0.507*CN - 0.00374*CN^2 + 0.0000867*CN^3 (rounded) ; CN_wet = 5.6*10^-14 + 2.33*CN - 0.0209*CN^2 + 0.000076*CN^3 (rounded)
       Weighted wetness of top zCN depth: weights per compartment wrel_i = wx_i - wx_{i-1}, wx_i = 1.016*(1 - exp(-4.16*(z_i/zCN))) (clipped 0-1); wet_top = sum wrel_i*(theta_i - theta_wp_i)/(theta_fc_i - theta_wp_i) (clipped 0-1)
       CN = round(CN_dry + (CN_wet - CN_dry)*wet_top) ; S = 25400/CN - 254 [mm] ; Ia = 0.05*S
       Runoff Q = (P - Ia)^2 / (P + 0.95*S) if P > Ia else 0 ; Infiltration = P - Q
       Management: CN adjusted by (1 + pct/100); if bunds with height > 1 mm or runoff inhibition -> Q = 0 (water ponds as surface storage up to bund height).
 (c) Soil evaporation (two-stage, Ritchie-type via REW):
       Kex = max soil evaporation coefficient (default 1.1); fwcc canopy-shade adjustment (default 50 %).
       EsPot = Kex*(1 - CCadj)*ET0 ; capped by EsPotMax = Kex*ET0*(1 - CCxW*fwcc/100) ; during senescence (t > Senescence and CCxAct>0) EsPot *= (1 - CCxAct*fwcc/100*mult) with
           mult = 1 if CC <= CCxAct/2 ; 0 if CC > CCxAct ; else (CCxAct - CC)/(CCxAct/2); lower bound EsPotMin = Kex*(1 - CCxActAdj)*ET0 with CCxActAdj = 1.72*CCxAct - CCxAct^2 + 0.3*CCxAct^3
       Mulch: EsPot *= (1 - fMulch*mulchPct/100) when no surface ponding. Irrigation wetting fraction: if irrigated and no rain>1 mm and no ponding: EsPot *= WetSurf/100 ; take the min of mulch/wetting adjusted values.
       Stage 1 (energy-limited): evaporation from surface wetness Wsurf up to REW after wetting (Wsurf = min(Infl, REW)); extract from top EvapZmin layer water above air-dry.
       Stage 2 (falling rate): Kr = (exp(fevap*Wrel) - 1)/(exp(fevap) - 1) with Wrel = (W_act - W_dry)/(W_upper - W_dry) , W_upper = Wstage2*(W_sat - (W_fc - REW)) + (W_fc - REW);
           evaporation layer deepens from EvapZmin to EvapZmax (step 1 mm) when Wrel < fWrelExp*(EvapZmax - EvapZ)/(EvapZmax - EvapZmin); EsAct = Kr*EsPot limited by available water. Sub-daily iteration with EvapTimeSteps (default 20).
       Defaults [VERIFIED in source]: REW = 9.0 mm if not texture-adjusted, EvapZmin = 0.15 m, EvapZmax = 0.30 m, Kex = 1.1, fevap = 4, fWrelExp = 0.4, fwcc = 50 %, zCN = 0.3 m, zGerm = 0.3 m, fshape_cr = 16.
       Texture-based REW (literature, FAO-56 Table 19 - Codex must re-check against the table and ship as an editable CSV with provenance 'literature_FAO56'): sand 2-7, loamy sand 4-8, sandy loam 6-10, loam 8-10, silt loam 8-11, silty clay loam 8-11, silty clay 8-12, clay 8-12 (mm; use midpoint, carry +/- half-range as uncertainty).
 (d) Capillary rise from water table: Ksat-based steady upward flux using aCR, bCR per texture, limited by gradient; Level 1: IMPLEMENT but default OFF unless water_table_depth is provided (most Rajasthan farmland: deep water table -> negligible).
 (e) Root-zone water: TAW = 1000*sum_i (theta_fc_i - theta_wp_i)*dz_i*rootfrac_i ; Dr = 1000*sum_i (theta_fc_i - theta)*dz_i*rootfrac_i ; use the stricter of root-zone vs. topsoil (zTop) depletion fraction when computing stress (as in the crop code).
 (f) Irrigation application:  gross = net/eff_app ; net requirement = Dr (refill to FC) for SOIL_MOISTURE_THRESHOLD policy when Dr/TAW > (1 - SMT/100) ; max depth cap ; interval ; season cap ; schedule list; special mode NET (irrigate to keep the SMT) ; rainfall forecast skip rule (optional extension: skip if forecast rain >= 0.5*Dr in next 48 h with probability >= 0.7).

 Level 2 extension (SoilWaterModel.supports adds "richards"): 1-D Richards equation with Mualem-van Genuchten via an implicit finite-volume scheme (use scipy.integrate / or fipy-like own tridiagonal + Picard iteration) ONLY for plots where a measured retention/Ksat curve and sensors exist. Level 1 stays default.
 Tile/lateral drainage (optional, off by default): remove water from layers between drain depth and target level at rate coefficient.

 MASS BALANCE (hard test): sum(P + Irr + CR + GWin) - sum(Runoff + Es + Tr + DeepPerc + TileDrain) = dStorage(soil + surface) within 0.5 mm per season (assert; raise MassBalanceError).
 API: class LayeredWaterBalance: step(state, forcing: DailyForcing, actions) -> (new_state, fluxes) ; pure functions per process listed above (drainage(), curve_number_runoff(), soil_evaporation(), infiltration(), root_zone_water()) so each is unit-testable alone.
TESTS: (1) bucket test: no crop, no rain, no ET -> state unchanged; (2) saturated column drains to FC in a time consistent with tau (analytic for one layer: theta(t) relation via the exponential drainage law integrated numerically); (3) curve number: P=50 mm, CN=75 -> S=84.67 mm, Ia=4.23, Q=(50-4.23)^2/(50+0.95*84.67)=16.1 mm (hand-check to 0.05 mm); (4) mass balance 10-year random-forcing run closes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from farm_twin.core.errors import MassBalanceError


class WaterLayer(BaseModel):
    top_m: float
    bottom_m: float
    theta: float
    theta_wp: float
    theta_fc: float
    theta_sat: float
    ksat_mm_day: float
    tau: float

    @property
    def depth_mm(self) -> float:
        return (self.bottom_m - self.top_m) * 1000


class WaterColumn(BaseModel):
    layers: list[WaterLayer]
    surface_storage_mm: float = 0

    def storage_mm(self) -> float:
        return self.surface_storage_mm + sum(layer.theta * layer.depth_mm for layer in self.layers)


class DailyForcing(BaseModel):
    rain_mm: float = 0
    et0_mm: float = 0
    irrigation_gross_mm: float = 0
    irrigation_efficiency: float = 1
    crop_transpiration_demand_mm: float = 0
    canopy_cover: float = 0
    curve_number: float = 75
    cn_adjust_pct: float = 0
    bund_height_mm: float = 0
    mulch_pct: float = 0
    rew_mm: float = 9
    kex: float = 1.1


class WaterFluxes(BaseModel):
    runoff_mm: float = 0
    infiltration_mm: float = 0
    drainage_mm: float = 0
    deep_percolation_mm: float = 0
    evaporation_mm: float = 0
    transpiration_mm: float = 0
    irrigation_net_mm: float = 0
    residual_mm: float = 0


@dataclass(frozen=True)
class RootZoneWater:
    taw_mm: float
    depletion_mm: float


def curve_number_runoff(
    rain_mm: float,
    curve_number: float,
    wetness: float | None = None,
    cn_adjust_pct: float = 0,
    bund_height_mm: float = 0,
) -> tuple[float, float]:
    if rain_mm < 0 or not 0 < curve_number <= 100:
        raise ValueError("rainfall and curve number outside physical limits")
    cn = min(100, max(1, curve_number * (1 + cn_adjust_pct / 100)))
    if wetness is not None:
        cn_dry = round(1.4e-14 + 0.507 * cn - 0.00374 * cn**2 + 0.0000867 * cn**3)
        cn_wet = round(5.6e-14 + 2.33 * cn - 0.0209 * cn**2 + 0.000076 * cn**3)
        cn = min(100, max(1, round(cn_dry + (cn_wet - cn_dry) * min(1, max(0, wetness)))))
    storage = 25400 / cn - 254
    initial_abstraction = 0.05 * storage
    runoff = (rain_mm - initial_abstraction) ** 2 / (rain_mm + 0.95 * storage) if rain_mm > initial_abstraction else 0
    if bund_height_mm > 1:
        runoff = 0.0
    runoff = min(rain_mm, max(0.0, runoff))
    return runoff, rain_mm - runoff


def drainage(layers: list[WaterLayer]) -> tuple[list[WaterLayer], float]:
    """Drain layers top-down, conserving water and limiting downward transfer by capacity."""
    updated = [layer.model_copy(deep=True) for layer in layers]
    incoming = 0.0
    deep_loss = 0.0
    for i, layer in enumerate(updated):
        amount, incoming = incoming, 0.0
        if amount:
            accepted = min(amount, max(0.0, (layer.theta_sat - layer.theta) * layer.depth_mm), layer.ksat_mm_day)
            layer.theta += accepted / layer.depth_mm
            amount -= accepted
            if amount and i > 0:
                updated[i - 1].theta += amount / updated[i - 1].depth_mm
        if layer.theta <= layer.theta_fc:
            continue
        excess = (layer.theta - layer.theta_fc) * layer.depth_mm
        saturation_excess = max(0.0, (layer.theta_sat - layer.theta_fc) * layer.depth_mm)
        if saturation_excess <= 0:
            continue
        denominator = math.exp(min(50, layer.theta_sat - layer.theta_fc)) - 1
        proposed = (
            layer.tau * saturation_excess * (math.exp(min(50, layer.theta - layer.theta_fc)) - 1) / (denominator or 1)
        )
        out = min(excess, proposed, layer.ksat_mm_day)
        layer.theta -= out / layer.depth_mm
        if i + 1 < len(updated):
            incoming = out
        else:
            deep_loss += out
    return updated, deep_loss


def root_zone_water(layers: list[WaterLayer], root_depth_m: float) -> RootZoneWater:
    taw = depletion = 0.0
    for layer in layers:
        depth = max(0.0, min(layer.bottom_m, root_depth_m) - layer.top_m)
        taw += (layer.theta_fc - layer.theta_wp) * depth * 1000
        depletion += (layer.theta_fc - layer.theta) * depth * 1000
    return RootZoneWater(taw, depletion)


class LayeredWaterBalance:
    def __init__(self, *, mass_balance_tolerance_mm: float = 0.5) -> None:
        self.mass_balance_tolerance_mm = mass_balance_tolerance_mm

    def step(
        self, state: WaterColumn, forcing: DailyForcing, actions: dict[str, Any] | None = None
    ) -> tuple[WaterColumn, WaterFluxes]:
        before = state.storage_mm()
        new = state.model_copy(deep=True)
        irrigation_net = forcing.irrigation_gross_mm * forcing.irrigation_efficiency
        rz = root_zone_water(new.layers, new.layers[-1].bottom_m)
        wetness = min(1.0, max(0.0, rz.depletion_mm / max(1e-9, rz.taw_mm)))
        runoff, infiltration = curve_number_runoff(
            forcing.rain_mm, forcing.curve_number, wetness, forcing.cn_adjust_pct, forcing.bund_height_mm
        )
        water = infiltration + irrigation_net
        for layer in new.layers:
            accepted = min(water, max(0.0, (layer.theta_sat - layer.theta) * layer.depth_mm), layer.ksat_mm_day)
            layer.theta += accepted / layer.depth_mm
            water -= accepted
            if water <= 1e-12:
                break
        new.surface_storage_mm = max(0.0, new.surface_storage_mm + water)
        new.layers, deep = drainage(new.layers)
        cc = min(1.0, max(0.0, forcing.canopy_cover))
        es_pot = forcing.kex * (1 - cc) * forcing.et0_mm * max(0.0, 1 - forcing.mulch_pct / 100)
        es = min(es_pot, max(0.0, (new.layers[0].theta - new.layers[0].theta_wp) * new.layers[0].depth_mm))
        new.layers[0].theta -= es / new.layers[0].depth_mm
        tr_demand = max(0.0, forcing.crop_transpiration_demand_mm)
        tr = 0.0
        for layer in new.layers:
            take = min(max(0.0, (layer.theta - layer.theta_wp) * layer.depth_mm), tr_demand - tr)
            layer.theta -= take / layer.depth_mm
            tr += take
            if tr >= tr_demand:
                break
        after = new.storage_mm()
        residual = forcing.rain_mm + irrigation_net - runoff - deep - es - tr - (after - before)
        if abs(residual) > self.mass_balance_tolerance_mm:
            raise MassBalanceError("Daily water balance failed", context={"residual_mm": residual})
        flux = WaterFluxes(
            runoff_mm=runoff,
            infiltration_mm=infiltration,
            drainage_mm=deep,
            deep_percolation_mm=deep,
            evaporation_mm=es,
            transpiration_mm=tr,
            irrigation_net_mm=irrigation_net,
            residual_mm=residual,
        )
        return new, flux
