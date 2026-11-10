"""
FILE: farm_twin/models/solar/pv_engine.py
PURPOSE: Hourly PV energy model for any plot (ground fixed, single-axis tracker, elevated agrivoltaic, vertical bifacial, rooftop). Original implementation of the chain below; the `pvlib` package MAY be used as an optional cross-check dependency in tests only.

CHAIN (hourly, tz-aware timestamps, site lat/lon/elevation):
 1. SOLAR POSITION: NREL SPA-class accuracy not required; implement Michalsky/Meeus-grade algorithm (error < 0.01 deg): Julian day -> mean longitude L, mean anomaly g, ecliptic longitude lambda, obliquity eps, right ascension, declination, equation of time, hour angle, zenith/azimuth (azimuth from north, clockwise), refraction correction for apparent elevation. Validate at Jodhpur (26.2389 N, 73.0243 E): solar noon zenith on 2026-06-21 = 5.39 deg, on 2026-12-21 = 50.00 deg, on 2026-03-21 = 26.20 deg (reference outputs from an independent library, tolerance 0.1 deg).
 2. EXTRATERRESTRIAL: dni_extra = 1367*(1 + 0.033*cos(2*pi*doy/365)) W/m2.
 3. IRRADIANCE INPUT: measured/provider GHI (+ DNI, DHI if available); else DECOMPOSE GHI -> DHI via Erbs: kt = GHI/(E0*cos(zenith)); DHI/GHI = 1 - 0.09 kt (kt<=0.22); 0.9511 - 0.1604 kt + 4.388 kt^2 - 16.638 kt^3 + 12.336 kt^4 (0.22<kt<=0.80); 0.165 (kt>0.80); DNI = (GHI - DHI)/cos(zenith). Clear-sky model for gap-filling/planning: Ineichen-Perez or Haurwitz GHI = 1098*cos(z)*exp(-0.059/cos(z)) (Haurwitz; simple fallback). Aerosol in Rajasthan is high -> clear-sky overestimates; use measured GHI/ERA5 where possible.
 4. TRANSPOSITION to plane of array (POA): beam = DNI*cos(AOI), cos(AOI) = cos(z)cos(tilt) + sin(z)sin(tilt)cos(az_sun - az_panel); diffuse by PEREZ (1990) anisotropic model: coefficients table F11..F23 by epsilon bin (8 bins), brightness delta, clearness epsilon = ((DHI + DNI)/DHI + 1.041 z^3)/(1 + 1.041 z^3) (z radians): F1 = max(0, F11 + F12*delta + F13*z), F2 = F21 + F22*delta + F23*z ; E_d = DHI*[(1 - F1)*(1 + cos(tilt))/2 + F1*a/b + F2*sin(tilt)] with a = max(0,cos(AOI)), b = max(cos(85deg), cos(z)). Fallback isotropic: DHI*(1+cos(tilt))/2. Ground reflected: GHI*albedo*(1 - cos(tilt))/2 (albedo default 0.25 for dry soil; user-set). Codex: the Perez coefficient table (1990 'allsites') must be typed from the original paper; add a unit test comparing with an independent library on 24 hourly points to 1 W/m2.
 5. INCIDENCE-ANGLE MODIFIER: ASHRAE b0 = 0.05: IAM = 1 - b0*(1/cos(AOI) - 1) for beam; diffuse/ground IAM via effective angles (Brandemuehl-Beckman): theta_eff_sky = 59.7 - 0.1388*tilt + 0.001497*tilt^2 ; theta_eff_ground = 90 - 0.5788*tilt + 0.002693*tilt^2 (degrees; literature - verify).
 6. SOILING: loss fraction accumulates with dry days (rate prior 0.2-0.5 %/day in Rajasthan dust belt, calibratable), reset by rain >= 5 mm (partial 'cleaning efficiency' 0.8?) or manual cleaning events; cleaning cost goes to finance.
 7. CELL TEMPERATURE: Faiman: Tcell = Tamb + G/(U0 + U1*wind), U0 = 25 W/m2K, U1 = 6.84 W s/m3K (open rack defaults; flag), OR SAPM: Tm = G*exp(a + b*ws) + Tamb ; Tcell = Tm + G/1000*dT (open rack glass/glass a=-3.47,b=-0.0594,dT=3 ; close-roof mount glass/glass a=-2.98,b=-0.0471,dT=1) - literature, verify. Use wind at module height (2 m->10 m conversion). NOTE: elevated agrivoltaic arrays have high cooling -> open_rack parameters.
 8. DC POWER (PVWatts form): P_dc = (G_eff/1000)*Pdc0*(1 + gamma*(Tcell - 25)), gamma = -0.004 /K (crystalline silicon prior; datasheet value preferred).
    BIFACIAL: G_eff = G_front + bifaciality*G_rear*(1 - rear_shading_loss), rear irradiance from the view-factor model in agrivoltaic/ground_radiation.py (ground-reflected + sky seen from the rear).
 9. LOSSES (multiplicative, each configurable): soiling (above), mismatch 2 %, wiring DC 2 %, connections 0.5 %, nameplate 1 %, light-induced degradation 1.5 % (first year), availability 3 %; defaults flagged.
10. INVERTER (PVWatts form): eta_nom 0.96, eta_ref 0.9637; zeta = P_dc/Pdc0_inverter; eta = eta_nom/eta_ref*(-0.0162*zeta - 0.0059/zeta + 0.9858) ; P_ac = min(eta*P_dc, Pac0) ; zero below ~0.1% power (reference form; keep as published; verify against test).
11. DEGRADATION: P(t) = P0*(1 - d)^t, d default 0.005/yr (datasheet/ warranty-based; user-set); year-1 LID separately.
12. ANNUAL ENERGY: sum hourly AC; also specific yield kWh/kWp, performance ratio PR = E_ac/(H_poa * Pdc0/1000/ ... ) = E_ac/(Pdc0_kW * H_poa_kWh_m2/1 kW/m2).
13. UNCERTAINTY: interannual (use weather scenarios), model uncertainty (+/- 3-5 % transposition+temperature; priors), soiling (distribution), degradation (triangular 0.3-0.8 %/yr).
GOLDEN (clear-sky Jodhpur, 1 kWp, tilt 26, south, albedo 0.25, SAPM open-rack glass/glass, Tamb 30, wind 2 m/s, gamma -0.004, inverter Pac0 1000 W, daily sums): 2026-03-21 GHI 6.58 kWh/m2, POA 7.40, DC 6.52 kWh, AC 6.25 kWh ; 2026-06-21 GHI 7.67, POA 6.83, DC 6.10, AC 5.85 ; 2026-12-21 GHI 4.05, POA 6.08, DC 5.41, AC 5.20. Tolerance: GHI/POA +/-2 %, DC/AC +/-3 % (clear-sky model, transposition and turbidity choices differ).
TESTS: solar position, Erbs piecewise continuity, Perez vs fixtures, AOI at known geometry, energy conservation (AC <= DC <= POA*Pdc0 scale).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


PEREZ = {
    "epsilon": [1.065, 1.23, 1.5, 1.95, 2.8, 4.5, 6.2, 100],
    "F11": [-0.008, 0.13, 0.33, 0.568, 0.873, 1.132, 1.06, 0.678],
    "F12": [0.588, 0.683, 0.487, 0.187, -0.392, -1.237, -1.6, -0.327],
    "F13": [-0.062, -0.151, -0.221, -0.295, -0.362, -0.412, -0.359, -0.25],
    "F21": [-0.06, -0.019, 0.055, 0.109, 0.226, 0.288, 0.264, 0.156],
    "F22": [0.072, 0.066, -0.064, -0.152, -0.462, -0.823, -1.127, -1.377],
    "F23": [-0.022, -0.029, -0.026, -0.014, 0.001, 0.056, 0.131, 0.251],
}


def solar_position(times: pd.DatetimeIndex, latitude_deg: float, longitude_deg: float) -> pd.DataFrame:
    if times.tz is None:
        raise ValueError("solar position requires timezone-aware timestamps")
    local = times
    doy = local.dayofyear.to_numpy(dtype=float)
    hour = (local.hour + local.minute / 60 + local.second / 3600).to_numpy(dtype=float)
    gamma = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma)
        - 0.040849 * np.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.00148 * np.sin(3 * gamma)
    )
    offset_min = np.array([x.utcoffset().total_seconds() / 60 for x in local.to_pydatetime()])
    time_offset = eqtime + 4 * longitude_deg - offset_min
    tst = hour * 60 + time_offset
    ha = np.deg2rad(tst / 4 - 180)
    lat = np.deg2rad(latitude_deg)
    cosz = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha)
    zenith = np.rad2deg(np.arccos(np.clip(cosz, -1, 1)))
    azimuth = (np.rad2deg(np.arctan2(np.sin(ha), np.cos(ha) * np.sin(lat) - np.tan(decl) * np.cos(lat))) + 180) % 360
    elevation = 90 - zenith
    # NOAA refraction correction for apparent elevation.
    refr = np.where(
        elevation > 85,
        0,
        np.where(
            elevation > 5,
            (
                58.1 / np.tan(np.deg2rad(elevation))
                - 0.07 / np.tan(np.deg2rad(elevation)) ** 3
                + 0.000086 / np.tan(np.deg2rad(elevation)) ** 5
            )
            / 3600,
            np.where(
                elevation > -0.575,
                (1735 + elevation * (-518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711)))) / 3600,
                (-20.772 / np.tan(np.deg2rad(elevation))) / 3600,
            ),
        ),
    )
    return pd.DataFrame(
        {
            "zenith_deg": zenith,
            "azimuth_deg": azimuth,
            "elevation_deg": elevation + refr,
            "equation_of_time_min": eqtime,
        },
        index=times,
    )


def erbs_diffuse(ghi_w_m2: float, zenith_deg: float, day_of_year: int) -> tuple[float, float]:
    if ghi_w_m2 <= 0 or zenith_deg >= 90:
        return 0.0, 0.0
    extra = 1367 * (1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365))
    cosz = max(0.065, math.cos(math.radians(zenith_deg)))
    kt = max(0, ghi_w_m2 / (extra * cosz))
    if kt <= 0.22:
        kd = 1 - 0.09 * kt
    elif kt <= 0.8:
        kd = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    else:
        kd = 0.165
    dhi = min(ghi_w_m2, max(0, kd * ghi_w_m2))
    dni = max(0, (ghi_w_m2 - dhi) / cosz)
    return dni, dhi


def perez_diffuse(
    dhi_w_m2: float, dni_w_m2: float, zenith_deg: float, tilt_deg: float, aoi_deg: float, dni_extra_w_m2: float
) -> float:
    z = math.radians(min(90, zenith_deg))
    if dhi_w_m2 <= 1e-9:
        return 0.0
    delta = dhi_w_m2 / (max(1e-9, math.cos(z)) * max(1e-9, dni_extra_w_m2))
    epsilon = ((dhi_w_m2 + dni_w_m2) / dhi_w_m2 + 1.041 * z**3) / (1 + 1.041 * z**3)
    idx = next((i for i, edge in enumerate(PEREZ["epsilon"]) if epsilon <= edge), 7)
    f1 = max(0, PEREZ["F11"][idx] + PEREZ["F12"][idx] * delta + PEREZ["F13"][idx] * z)
    f2 = PEREZ["F21"][idx] + PEREZ["F22"][idx] * delta + PEREZ["F23"][idx] * z
    a = max(0, math.cos(math.radians(aoi_deg)))
    b = max(math.cos(math.radians(85)), math.cos(z))
    tilt = math.radians(tilt_deg)
    return max(0, dhi_w_m2 * ((1 - f1) * (1 + math.cos(tilt)) / 2 + f1 * a / b + f2 * math.sin(tilt)))


def ashrae_iam(aoi_deg: float, b0: float = 0.05) -> float:
    cosine = math.cos(math.radians(aoi_deg))
    if cosine <= 0:
        return 0.0
    return max(0.0, 1 - b0 * (1 / cosine - 1))


def pvwatts_hourly(
    weather: pd.DataFrame,
    *,
    latitude_deg: float,
    longitude_deg: float,
    tilt_deg: float,
    azimuth_deg: float = 180,
    pdc0_w: float = 1000,
    gamma_pdc_per_C: float = -0.004,
    pac0_w: float | None = None,
    albedo: float = 0.25,
    inverter_eta: float = 0.96,
    wind_col: str = "wind_ms",
    tamb_col: str = "temp_air_c",
    b0: float = 0.05,
    losses: dict[str, float] | None = None,
    soiling_loss: float = 0.0,
) -> pd.DataFrame:
    if not isinstance(weather.index, pd.DatetimeIndex) or weather.index.tz is None:
        raise ValueError("weather needs a tz-aware DatetimeIndex")
    pos = solar_position(weather.index, latitude_deg, longitude_deg)
    out = weather.copy()
    out["zenith_deg"], out["solar_azimuth_deg"] = pos.zenith_deg, pos.azimuth_deg
    ghi = (
        out["ghi_w_m2"].to_numpy(dtype=float)
        if "ghi_w_m2" in out
        else 1098
        * np.maximum(0, np.cos(np.deg2rad(pos.zenith_deg)))
        * np.exp(-0.059 / np.maximum(0.01, np.cos(np.deg2rad(pos.zenith_deg))))
    )
    dni, dhi = [], []
    for g, z, doy in zip(ghi, pos.zenith_deg, weather.index.dayofyear):
        a, b = erbs_diffuse(float(g), float(z), int(doy))
        dni.append(a)
        dhi.append(b)
    dni, dhi = np.asarray(dni), np.asarray(dhi)
    zen = np.deg2rad(pos.zenith_deg.to_numpy())
    tilt = math.radians(tilt_deg)
    azdiff = np.deg2rad(pos.azimuth_deg.to_numpy() - azimuth_deg)
    cos_aoi = np.cos(zen) * math.cos(tilt) + np.sin(zen) * math.sin(tilt) * np.cos(azdiff)
    aoi = np.rad2deg(np.arccos(np.clip(cos_aoi, -1, 1)))
    poa_beam = dni * np.maximum(0, cos_aoi) * np.array([ashrae_iam(a, b0) for a in aoi])
    poa_diff = np.array(
        [
            perez_diffuse(d, n, z, tilt_deg, ao, 1367 * (1 + 0.033 * math.cos(2 * math.pi * doy / 365)))
            for d, n, z, ao, doy in zip(dhi, dni, pos.zenith_deg, aoi, weather.index.dayofyear)
        ]
    )
    poa_ground = ghi * albedo * (1 - math.cos(tilt)) / 2
    poa = poa_beam + poa_diff + poa_ground
    temp = out[tamb_col].to_numpy(dtype=float) if tamb_col in out else np.full(len(out), 25.0)
    wind = out[wind_col].to_numpy(dtype=float) if wind_col in out else np.full(len(out), 1.0)
    tcell = temp + poa / (25 + 6.84 * np.maximum(0, wind))
    pdc = (poa / 1000) * pdc0_w * (1 + gamma_pdc_per_C * (tcell - 25))
    loss = losses or {
        "mismatch": 0.02,
        "wiring": 0.02,
        "connections": 0.005,
        "nameplate": 0.01,
        "lid": 0.015,
        "availability": 0.03,
    }
    factor = math.prod(1 - min(0.99, max(0, x)) for x in loss.values()) * (1 - min(0.99, max(0, soiling_loss)))
    pdc *= factor
    inv = max(1e-9, pac0_w if pac0_w is not None else pdc0_w)
    zeta = pdc / inv
    eta = np.where(zeta > 0, inverter_eta / 0.9637 * (-0.0162 * zeta - 0.0059 / np.maximum(zeta, 1e-9) + 0.9858), 0)
    pac = np.minimum(np.maximum(eta * pdc, 0), inv)
    pac = np.where(pac < 0.001 * inv, 0, pac)
    hours = weather.index.to_series().diff().dt.total_seconds().div(3600).median()
    if pd.isna(hours) or hours <= 0:
        hours = 1.0
    out["dni_w_m2"], out["dhi_w_m2"], out["poa_w_m2"] = dni, dhi, poa
    out["tcell_c"], out["pdc_w"], out["pac_w"] = tcell, pdc, pac
    out["energy_kwh"] = pac * hours / 1000
    out.attrs.update(
        fidelity="L1_SPEC",
        Perez="allsites coefficients",
        clear_sky_fallback="Haurwitz",
        warning="temperature, soiling, and loss defaults require local/datasheet calibration",
    )
    return out
