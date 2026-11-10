"""
FILE: farm_twin/models/agrivoltaic/ground_radiation.py
PURPOSE: Radiation (and PAR) reaching the crop BENEATH and BETWEEN PV rows, per ground position and per hour. NEW MODULE - no existing open-source crop model supplies this; it is the bridge between the PV and crop engines.

GEOMETRY (2-D cross-section perpendicular to row axis; infinite rows; x across rows, z up):
  each row = a straight strip (collector) of slant width Wc, tilt beta, azimuth gamma_p; strip lower edge at height h0 (clearance), upper edge at h0 + Wc*sin(beta); horizontal projection w = Wc*cos(beta); repeats every pitch P.
  ground sample points: x_k, k = 0..K-1 across one pitch (default dx = 0.10 m -> keep K <= 400 by capping resolution), ground point positions relative to the row axis.
DIRECT BEAM SHADOW (per hour with sun elevation alpha > 2 deg):
  sun vector s = (cos(alpha)*sin(azs), cos(alpha)*cos(azs), sin(alpha)) (E,N,Up). Row axis direction a = (sin(row_az), cos(row_az), 0). Work in the plane perpendicular to a: apparent profile angle of the sun in that plane  phi = atan2(s_perp_x, s_z) where s_perp_x is the component of s along the cross-row horizontal direction n = (cos(row_az), -sin(row_az), 0)... (Codex: derive and unit-test with brute-force 3-D ray casting on a few geometries; the 2-D profile-angle result must match ray casting within 1 % area.)
  shadow of the collector strip's two edges on the ground plane: x_edge = x_edge_top - z_edge * tan(phi) ; shaded interval = [min, max] of the two projected edges (+ periodic copies at +/- P, +/- 2P ...). Ground point x_k is directly shaded if inside any copy interval -> beam transmittance tau_beam(x_k, t) = tau_panel (0 opaque; 0.0-0.5 semi-transparent / gaps between modules: ADD `module_gap_fraction`, effective tau = gap_fraction + (1-gap_fraction)*cell_transmittance).
DIFFUSE SKY at ground point (isotropic sky approx, Level 1): sky view factor SVF(x_k) = 1 - sum_over_strips (sin(theta_2) - sin(theta_1))/2 where theta_1, theta_2 are the angles (from vertical, in the cross-row plane) subtended by each strip's two edges as seen from x_k, signed, restricted to the sky hemisphere; the 2-D result is exact for a horizontal receiver and infinite parallel strips. For anisotropic sky use circumsolar+horizon-brightening decomposition: Level 2 (document, not required).
   Panel contribution: radiation transmitted through semi-transparent modules adds tau_diff*DHI*(portion).
REFLECTED from ground between rows / from panels' underside: Level 1 ignores panel-underside emission; ground-to-ground reflection neglected; albedo effect included only for bifacial rear side (view factor ground->rear).
GROUND GHI (per point, hour): G_g(x_k,t) = DNI*cos(zenith)*tau_beam(x_k,t) + DHI*SVF(x_k) [+ transmitted terms].
PAR: PAR = f_par * G_g with f_par default 0.45 (0.43-0.50 range; flagged) - and spectral modification for semi-transparent PV via module PAR transmittance parameter.
AGGREGATION: daily sums per position and per CROP STRIP (crops rows occupy specified x-intervals): radiation fraction Frad(x,day) = sum G_g / sum GHI_open ; mean over crop strip weighted by planting area. Output arrays [day, x_k]; store only the strip-averaged series plus the full profile for 5 representative days per season (for UI).
EDGE EFFECTS & FIELD ENDS: finite-row length ignored L1 (document: plot of 6-12 m length has end effects; flag results as 'upper bound on shading' for rows shorter than 4*h0).
CALIBRATION POINTS: user may upload PAR/lux-meter or ceptometer readings under panels (MEASURED) -> fit tau_eff and f_par by least squares; calibration module stores residuals.
OUTPUT: GroundRadiation(frad_daily_by_strip, par_daily_by_strip_MJ_m2, shade_hours_by_position, svf_profile).
VALIDATION: (1) no panels -> Frad = 1; (2) panel directly overhead at noon at beta=0 -> ground under panel fully shaded for beam; (3) energy sanity: area-averaged beam transmittance with opaque horizontal panel of width w and pitch P at sun overhead = 1 - w/P ; (4) SVF at the point beneath the center of a horizontal infinite strip of width 2a at height h = 1 - sin(atan(a/h)) (check formula = 1 - a/sqrt(a^2+h^2)); (5) brute-force ray-casting oracle test (tests/oracle_raycast.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GroundRadiation:
    frad_daily_by_strip: np.ndarray
    par_daily_by_strip_MJ_m2: np.ndarray
    shade_hours_by_position: np.ndarray
    svf_profile: np.ndarray
    radiation_profile_MJ_m2: np.ndarray
    fidelity: str = "L1_SPEC_ISOTROPIC_DIFFUSE"


def _svf_one(x: float, pitch_m: float, clearance_m: float, width_m: float, tilt_deg: float, n_copies: int = 3) -> float:
    beta = np.deg2rad(tilt_deg)
    blocked = 0.0
    for k in range(-n_copies, n_copies + 1):
        x0 = k * pitch_m
        x1 = x0 + width_m * np.cos(beta)
        z0 = clearance_m
        z1 = clearance_m + width_m * np.sin(beta)
        t0 = np.arctan2(x0 - x, z0)
        t1 = np.arctan2(x1 - x, z1)
        blocked += abs(np.sin(t1) - np.sin(t0)) / 2
    return float(np.clip(1 - blocked, 0, 1))


def ground_radiation(
    dni_w_m2: np.ndarray,
    dhi_w_m2: np.ndarray,
    zenith_deg: np.ndarray,
    solar_azimuth_deg: np.ndarray,
    *,
    row_azimuth_deg: float,
    collector_width_slant_m: float,
    tilt_deg: float,
    pitch_m: float,
    clearance_m: float,
    dx_m: float = 0.1,
    module_gap_fraction: float = 0,
    cell_transmittance: float = 0,
    f_par: float = 0.45,
    crop_strips: list[tuple[float, float]] | None = None,
) -> GroundRadiation:
    arrays = [np.asarray(a, dtype=float) for a in (dni_w_m2, dhi_w_m2, zenith_deg, solar_azimuth_deg)]
    if not all(len(a) == len(arrays[0]) for a in arrays) or pitch_m <= 0 or collector_width_slant_m < 0:
        raise ValueError("hourly inputs must have equal lengths and valid panel geometry")
    if collector_width_slant_m == 0:
        points = np.arange(0, pitch_m, max(dx_m, pitch_m / 400))
        if len(points) == 0:
            points = np.array([0.0])
        open_ghi = arrays[0] * np.maximum(0, np.cos(np.deg2rad(arrays[2]))) + arrays[1]
        daily = open_ghi.sum() * 3600 / 1e6
        par = np.full((1, 1), daily * f_par)
        return GroundRadiation(
            np.ones((1, 1)), par, np.zeros(len(points)), np.ones(len(points)), np.full((1, len(points)), daily)
        )
    dx = max(dx_m, pitch_m / 400)
    x = np.arange(0, pitch_m, dx)
    if len(x) > 400:
        x = x[:400]
    svf = np.array([_svf_one(float(xx), pitch_m, clearance_m, collector_width_slant_m, tilt_deg) for xx in x])
    beta = np.deg2rad(tilt_deg)
    w = collector_width_slant_m * np.cos(beta)
    rise = collector_width_slant_m * np.sin(beta)
    transmittance = min(1, max(0, module_gap_fraction + (1 - module_gap_fraction) * cell_transmittance))
    profile = []
    open_total = 0.0
    shade_hours = np.zeros(len(x))
    for dni, dhi, zen, az in zip(*arrays):
        elev = 90 - zen
        if elev <= 2:
            beam = np.zeros(len(x))
        else:
            phi = np.arctan2(
                np.cos(np.deg2rad(elev)) * np.sin(np.deg2rad(az - row_azimuth_deg)), np.sin(np.deg2rad(elev))
            )
            tangent = np.tan(phi)
            xedges = np.array([0.0, w]) - np.array([clearance_m, clearance_m + rise]) * tangent
            shade = np.zeros(len(x), dtype=bool)
            for k in range(-2, 3):
                shade |= (x >= min(xedges) + k * pitch_m) & (x <= max(xedges) + k * pitch_m)
            tau = np.where(shade, transmittance, 1.0)
            beam = dni * max(0, np.cos(np.deg2rad(zen))) * tau
            shade_hours += shade.astype(float)
        g = beam + dhi * svf + transmittance * dhi * (1 - svf)
        profile.append(g)
        open_total += dni * max(0, np.cos(np.deg2rad(zen))) + dhi
    profiles = np.asarray(profile).T
    # Hour weights are one hour per sample; caller aggregates other intervals before invoking.
    daily_profile = profiles.sum(axis=1) * 0.0036
    open_daily = open_total * 0.0036
    if crop_strips:
        frad = []
        par = []
        for lo, hi in crop_strips:
            mask = (x >= lo) & (x <= hi)
            mean = float(np.mean(daily_profile[mask])) if mask.any() else 0
            frad.append(mean / max(open_daily, 1e-12))
            par.append(mean * f_par)
        frad_arr = np.asarray(frad)[None, :]
        par_arr = np.asarray(par)[None, :]
    else:
        frad_arr = np.array([[float(np.mean(daily_profile)) / max(open_daily, 1e-12)]])
        par_arr = np.array([[float(np.mean(daily_profile)) * f_par]])
    return GroundRadiation(frad_arr, par_arr, shade_hours, svf, daily_profile)
