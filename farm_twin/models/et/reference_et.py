"""
FILE: farm_twin/models/et/reference_et.py
PURPOSE: Reference evapotranspiration ET0 (mm/day). Crop model needs daily ET0; compute it OURSELVES from weather so provider ET0 is only a cross-check.

IMPLEMENT FAO-56 Penman-Monteith (daily), Level 1 REQUIRED:
  ET0 = [0.408*D*(Rn - G) + gamma*(900/(T+273))*u2*(es - ea)] / [D + gamma*(1 + 0.34*u2)]
    T = (Tmax+Tmin)/2 ; G = 0 for daily step
    es = (e0(Tmax)+e0(Tmin))/2 ; e0(T) = 0.6108*exp(17.27*T/(T+237.3)) [kPa]
    ea = from Tdew: e0(Tdew); else from RHmean: ea = RHmean/100*(e0(Tmax)+e0(Tmin))/2 ; else (no humidity) ea = e0(Tmin - K0) with K0 = 2 C (arid: use 4 C, FAO-56 allows) -> flag ESTIMATED_LOW_CONF
    D = 4098*e0(T)/(T+237.3)^2  [kPa/C]
    P = 101.3*((293 - 0.0065*z)/293)^5.26 ; gamma = 0.000665*P  [kPa/C]
    Ra (extraterrestrial): dr = 1 + 0.033*cos(2*pi*J/365); delta = 0.409*sin(2*pi*J/365 - 1.39); ws = arccos(-tan(phi)*tan(delta));
         Ra = (24*60/pi)*0.0820*dr*[ws*sin(phi)*sin(delta) + cos(phi)*cos(delta)*sin(ws)]  [MJ/m2/day]
    Rs: measured/provider; if missing -> Hargreaves-Samani Rs = kRs*sqrt(Tmax-Tmin)*Ra with kRs 0.16 interior / 0.19 coastal (ESTIMATED)
    Rso = (0.75 + 2e-5*z)*Ra ; Rns = (1-0.23)*Rs ; Rnl = sigma*((Tmax_K^4 + Tmin_K^4)/2)*(0.34 - 0.14*sqrt(ea))*(1.35*Rs/Rso - 0.35), sigma = 4.903e-9 MJ/K^4/m2/day (Rs/Rso clipped to [0.3,1.0])
    Rn = Rns - Rnl
    u2 from u10 per core wind conversion (providers/base.py)
  Fallback Level 1b (only if no wind/humidity): Hargreaves ET0 = 0.0023*(Tmean+17.8)*sqrt(Tmax-Tmin)*Ra/lambda... implement in mm/day as 0.0023*0.408*Ra*(Tmean+17.8)*sqrt(Tmax-Tmin); flag ESTIMATED with +/-15% uncertainty.
  API: et0_fao56(df, lat_deg, elev_m) -> Series with Quantified provenance; vectorised numpy; unit tests against FAO-56 worked example numbers (Example 18, Bangkok monthly and Example 19 daily Uccle: ET0 = 3.9 mm/day) - Codex: reproduce the published example inputs from the FAO-56 text/tables and assert to 0.05 mm/day.
  ALSO: et0_with_microclimate(df, rs_scale, u2_scale, dT) for the agrivoltaic coupling: recompute with Rs*rs_scale, u2*u2_scale, Tmax/Tmin + dT. (Radiation term is reduced under panels; wind term scaled; both effects are separately switchable for sensitivity analysis.)
TESTS: Uccle daily example; monotonicity (ET0 increases with Rs, u2, T); ET0 >= 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


SIGMA = 4.903e-9


def _sat_vapour_pressure(temp_c: np.ndarray) -> np.ndarray:
    return 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))


def extraterrestrial_radiation(day_of_year: np.ndarray, latitude_rad: float) -> np.ndarray:
    dr = 1 + 0.033 * np.cos(2 * np.pi * day_of_year / 365.0)
    delta = 0.409 * np.sin(2 * np.pi * day_of_year / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(latitude_rad) * np.tan(delta), -1.0, 1.0))
    return (
        (24 * 60 / np.pi)
        * 0.0820
        * dr
        * (ws * np.sin(latitude_rad) * np.sin(delta) + np.cos(latitude_rad) * np.cos(delta) * np.sin(ws))
    )


def et0_fao56(df: pd.DataFrame, lat_deg: float, elev_m: float) -> pd.Series:
    """Compute daily FAO-56 PM ET0 in mm/day; estimates are flagged in Series attrs."""
    data = df.copy()
    tmax = np.asarray(data["tmax_c"], dtype=float)
    tmin = np.asarray(data["tmin_c"], dtype=float)
    tmean = (tmax + tmin) / 2
    doy = np.asarray(pd.to_datetime(data["date"]).dt.dayofyear, dtype=float)
    lat = np.deg2rad(lat_deg)
    ra = extraterrestrial_radiation(doy, lat)
    estimated: list[str] = []
    if "rs_mj_m2" in data and data["rs_mj_m2"].notna().all():
        rs = np.asarray(data["rs_mj_m2"], dtype=float)
    else:
        rs = 0.16 * np.sqrt(np.maximum(tmax - tmin, 0)) * ra
        estimated.append("shortwave_radiation_hargreaves_samani")
    if "tdew_c" in data and data["tdew_c"].notna().all():
        ea = _sat_vapour_pressure(np.asarray(data["tdew_c"], dtype=float))
    elif all(col in data and data[col].notna().all() for col in ("rh_max_pct", "rh_min_pct")):
        rhmax = np.asarray(data["rh_max_pct"], dtype=float) / 100
        rhmin = np.asarray(data["rh_min_pct"], dtype=float) / 100
        ea = (_sat_vapour_pressure(tmin) * rhmax + _sat_vapour_pressure(tmax) * rhmin) / 2
    elif "rh_mean_pct" in data and data["rh_mean_pct"].notna().all():
        ea = (
            np.asarray(data["rh_mean_pct"], dtype=float)
            / 100
            * (_sat_vapour_pressure(tmax) + _sat_vapour_pressure(tmin))
            / 2
        )
    else:
        ea = _sat_vapour_pressure(tmin - 2)
        estimated.append("humidity_from_tmin_minus_2c")
    es = (_sat_vapour_pressure(tmax) + _sat_vapour_pressure(tmin)) / 2
    delta = 4098 * _sat_vapour_pressure(tmean) / (tmean + 237.3) ** 2
    pressure = 101.3 * ((293 - 0.0065 * elev_m) / 293) ** 5.26
    gamma = 0.000665 * pressure
    rso = (0.75 + 2e-5 * elev_m) * ra
    rns = 0.77 * rs
    ratio = np.clip(rs / np.maximum(rso, 1e-9), 0.3, 1.0)
    rnl = (
        SIGMA
        * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2)
        * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0)))
        * (1.35 * ratio - 0.35)
    )
    rn = rns - rnl
    if "u2_ms" in data and data["u2_ms"].notna().all():
        u2 = np.asarray(data["u2_ms"], dtype=float)
    elif "u10_ms" in data and data["u10_ms"].notna().all():
        u2 = np.asarray(data["u10_ms"], dtype=float) * 4.87 / np.log(67.8 * 10 - 5.42)
    else:
        hargreaves = 0.0023 * 0.408 * ra * (tmean + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0))
        out = pd.Series(np.maximum(hargreaves, 0), index=data.index, name="et0_mm_day")
        out.attrs.update(source="ESTIMATED", flags=[*estimated, "hargreaves_fallback"], uncertainty_relative=0.15)
        return out
    value = (0.408 * delta * rn + gamma * (900 / (tmean + 273)) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    out = pd.Series(np.maximum(value, 0), index=data.index, name="et0_mm_day")
    out.attrs.update(
        source="ESTIMATED" if estimated else "MODEL_PREDICTED", flags=estimated, equation="FAO-56 Penman-Monteith"
    )
    return out


def et0_with_microclimate(
    df: pd.DataFrame,
    rs_scale: float = 1.0,
    u2_scale: float = 1.0,
    dT: float = 0.0,
    lat_deg: float = 26.24,
    elev_m: float = 200.0,
) -> pd.Series:
    shaded = df.copy()
    if "rs_mj_m2" in shaded:
        shaded["rs_mj_m2"] = shaded["rs_mj_m2"] * rs_scale
    for col in ("tmax_c", "tmin_c"):
        shaded[col] = shaded[col] + dT
    if "u2_ms" in shaded:
        shaded["u2_ms"] = shaded["u2_ms"] * u2_scale
    return et0_fao56(shaded, lat_deg, elev_m)
