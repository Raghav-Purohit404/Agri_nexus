"""
FILE: farm_twin/models/agrivoltaic/crop_coupling.py
PURPOSE: Translate ground radiation + panel microclimate into inputs the crop/soil engines understand. EXPERIMENTAL (Fidelity L1-experimental; no peer-validated crop-response model is bundled; every result flagged `agrivoltaic_unvalidated` until local trial data exist).

COUPLING MECHANISMS (each independently switchable for sensitivity analysis):
 A. ATMOSPHERIC DEMAND: ET0_shaded = FAO-56 PM with Rs_ground = Frad*Rs, wind u2*wind_factor (panel rows reduce near-surface wind: prior 0.6-1.0, flagged), Tmax_shaded = Tmax + dT_max (prior -0.5 to -3 C), Tmin + dT_min (prior 0 to +1 C), RH slightly higher (optional +0..5 pts). Uses reference_et.et0_with_microclimate().
 B. LIGHT-LIMITED GROWTH: biomass increment dB = min(dB_water, RUE * fPAR_crop * PAR_ground) where dB_water is the standard water-driven increment (with Tr/ET0 using shaded ET0). RUE (g DM / MJ intercepted PAR) crop-specific, placeholder priors by C3/C4 (C3 ~ 2.5-3.0, C4 ~ 3.0-3.8 g/MJ PAR - literature ranges, flagged), calibratable. fPAR_crop = canopy cover CC (proxy) * (1 - 0.1*? ) -> use fPAR = 1 - exp(-0.7*LAI) with LAI estimated from CC by LAI = -ln(1 - CC)/0.7 -> equals CC; so simply fPAR = CC; document equivalence.
 C. SHADE-ADAPTIVE CROP RESPONSE (crops differ): shade tolerance parameter `shade_tol` in crop library (0 intolerant ... 1 tolerant): modifies HI and canopy expansion: CGC_shade = CGC*(1 + k_s*(1 - Frad)) with k_s>0 for shade-adapted leaf expansion (specific leaf area increase), bounded; HI penalty f_HI_shade = 1 - c_h*max(0, Frad_flowering_window - threshold)... CALIBRATION REQUIRED; defaults = no adaptation (k_s=0, c_h=0) and a warning.
 D. SOIL TEMPERATURE & MOISTURE: reduced Es via reduced radiation (already through ET0_shaded); soil temperature offset dT_soil for RothC and for emergence (GDD uses shaded air temperatures).
 E. RAIN REDISTRIBUTION: panel drip lines concentrate rain at the lower edge (extra water along the drip line; deficit beneath): implement as an optional multiplicative rain profile P(x) = P*(1 + c_r(x)) with mean 1 across pitch (c_r by geometry: collector catchment area Wc*L drained to the lower edge strip); default OFF; flagged.
 F. SPATIAL DISCRETISATION: split an agrivoltaic plot into strips (e.g. under-panel, edge, inter-row) each with its own Frad/ET0 -> run the crop engine per strip; plot yield = area-weighted average. Number of strips default 3, max 8.
 G. TRADE-OFF METRICS: relative yield RY = Y_AV/Y_open (same weather, same management); land equivalent ratio LER = RY + (E_AV / E_ground-mount reference) where E_ref is energy from a standard ground array occupying the same area at its own GCR; economic LER = revenue_AV / max(revenue_crop_open, revenue_PV_ground_reference). LER > 1 means joint use beats separate use of equal areas.
 H. OUTPUT: MicroclimateFactors(strip) = {frad, par_mj_m2_day, et0_scale, u2_scale, dTmax, dTmin, dT_soil}, plus list of active mechanisms and the calibration status.
LIMITS PRINTED WITH RESULTS: simplified light/water coupling; no crop-specific field-validated shade function; yield reductions are sensitive to RUE, shade_tol, k_s -> report them in the sensitivity analysis and require a trial plot before capital commitment.
TESTS: Frad=1, factors=1 -> identical to open-field run; yield monotone non-increasing with Frad reduction when light-limited; LER arithmetic; strips area weights sum to 1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MicroclimateFactors:
    frad: float
    par_mj_m2_day: float
    et0_scale: float
    u2_scale: float
    dTmax_c: float
    dTmin_c: float
    dT_soil_c: float
    active_mechanisms: tuple[str, ...]
    calibration_status: str = "EXPERIMENTAL_UNVALIDATED"


def microclimate_factors(
    frad: float,
    par_mj_m2_day: float,
    *,
    u2_scale: float = 1,
    dTmax_c: float = 0,
    dTmin_c: float = 0,
    dT_soil_c: float = 0,
    mechanisms: tuple[str, ...] = (),
) -> MicroclimateFactors:
    if not 0 <= frad <= 1 or par_mj_m2_day < 0 or u2_scale <= 0:
        raise ValueError("invalid agrivoltaic microclimate factors")
    return MicroclimateFactors(
        frad, par_mj_m2_day, frad, u2_scale, dTmax_c, dTmin_c, dT_soil_c, mechanisms, "EXPERIMENTAL_UNVALIDATED"
    )


def area_weighted_yield(yield_by_strip_t_ha: list[float], area_fraction_by_strip: list[float]) -> float:
    if len(yield_by_strip_t_ha) != len(area_fraction_by_strip) or not area_fraction_by_strip:
        raise ValueError("strip yields and fractions must align")
    if abs(sum(area_fraction_by_strip) - 1) > 1e-9 or any(f < 0 for f in area_fraction_by_strip):
        raise ValueError("strip area fractions must be non-negative and sum to 1")
    return sum(y * f for y, f in zip(yield_by_strip_t_ha, area_fraction_by_strip))


def ler(yield_av: float, yield_open: float, energy_av_kwh: float, energy_ground_ref_kwh: float) -> float:
    if yield_open <= 0 or energy_ground_ref_kwh <= 0:
        raise ValueError("open-field yield and reference energy must be positive")
    return yield_av / yield_open + energy_av_kwh / energy_ground_ref_kwh
