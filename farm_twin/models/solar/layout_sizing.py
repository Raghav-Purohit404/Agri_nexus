"""
FILE: farm_twin/models/solar/layout_sizing.py
PURPOSE: Turn plot geometry + PV config into capacity, rows, spacing, and shading-aware yield; tiny plots (55-120 m2) mean single-digit kWp systems.

IMPLEMENT:
  fixed-tilt row geometry: collector slant width Wc, tilt beta -> horizontal footprint w = Wc*cos(beta), height rise h = Wc*sin(beta); pitch P; GCR = Wc/P (ratio of collector width to pitch).
  row-to-row shading limit: minimum pitch to avoid shading at winter-solstice 9:00-15:00 solar time: P_min = Wc*(cos(beta) + sin(beta)/tan(alpha_s)) with alpha_s = sun elevation at the limiting hour (compute from solar position, not a fixed 'rule').
  fit_rows(plot_polygon_local, azimuth, Wc, beta, P, edge_setback): place rows along the long axis perpendicular to azimuth inside the setback-buffered polygon (shapely); modules per row = floor(row_length/module_width) * modules per collector; kWp = n_modules*module_Wp/1000.
  electrical sizing basics: DC/AC ratio 1.1-1.3 (default 1.2), string voltage within inverter MPPT window using Voc temperature correction (module params) - implement as checks returning issues, NOT an electrical design deliverable; code requires the user to confirm with a licensed installer.
  shading-aware yield: for each hour compute row-to-row shaded fraction (shadow overlap length on the next row: s = max(0, 1 - ((P - w)*... geometry) - implement via 2D projection of shadow edge using sun azimuth/elevation in the row-normal plane) and reduce POA beam by shaded fraction on the electrically-affected strings (assume bypass-diode granularity: each cell string loses proportionally in steps of n_substrings); diffuse unaffected except sky view factor reduction.
  tracker (single-axis N-S): rotation angle by astronomical tracking with backtracking (standard closed-form: tan(theta) = sin(z)sin(az - axis_az)/(cos(z)...) - implement from published single-axis tracking equations) - only as optional config; not default for tiny plots.
  CAPEX/OPEX hooks to finance/costs.py: capex = n_kWp*cost_per_kWp + structure + inverter + BoS + installation; elevated agrivoltaic structures cost more (user input; no hard-coded national price).
TESTS: GCR relation; P_min at beta=20 deg, Wc=2 m, alpha_s=25 deg => 2*(0.9397 + 0.3420/0.4663) = 3.35 m; rows fit count for a 10 m x 7.5 m plot.
"""

from __future__ import annotations

import math


def fixed_tilt_geometry(collector_width_slant_m: float, tilt_deg: float, pitch_m: float) -> dict[str, float]:
    if collector_width_slant_m <= 0 or pitch_m <= 0 or not 0 <= tilt_deg <= 90:
        raise ValueError("invalid row geometry")
    beta = math.radians(tilt_deg)
    return {
        "footprint_m": collector_width_slant_m * math.cos(beta),
        "rise_m": collector_width_slant_m * math.sin(beta),
        "gcr": collector_width_slant_m / pitch_m,
        "footprint_ratio": collector_width_slant_m * math.cos(beta) / pitch_m,
    }


def minimum_pitch_m(collector_width_slant_m: float, tilt_deg: float, sun_elevation_deg: float) -> float:
    if not 0 < sun_elevation_deg < 90:
        raise ValueError("sun elevation must be between 0 and 90 degrees")
    beta = math.radians(tilt_deg)
    alpha = math.radians(sun_elevation_deg)
    return collector_width_slant_m * (math.cos(beta) + math.sin(beta) / math.tan(alpha))


def fit_rows(
    polygon_local: object, azimuth_deg: float, collector_width_m: float, pitch_m: float, edge_setback_m: float = 0
) -> dict[str, float | int]:
    from shapely import affinity

    inset = polygon_local.buffer(-edge_setback_m) if edge_setback_m else polygon_local
    if inset.is_empty:
        return {"n_rows": 0, "area_m2": 0.0}
    # Rotate so row direction aligns to the geometry's x axis, then count pitch placements.
    rotated = affinity.rotate(inset, -(azimuth_deg - 90), origin="centroid", use_radians=False)
    minx, miny, maxx, maxy = rotated.bounds
    n = max(0, int(math.floor((maxy - miny) / pitch_m)))
    return {
        "n_rows": n,
        "row_length_m": maxx - minx,
        "area_m2": inset.area,
        "collector_width_m": collector_width_m,
        "pitch_m": pitch_m,
    }


def electrical_sizing_issues(
    module_voc_v: float,
    module_vmp_v: float,
    modules_series: int,
    inverter_mppt_min_v: float,
    inverter_mppt_max_v: float,
    temp_min_c: float = -10,
    voc_temp_coeff_per_C: float = -0.0028,
) -> list[str]:
    voc_cold = module_voc_v * (1 + voc_temp_coeff_per_C * (temp_min_c - 25)) * modules_series
    vmp = module_vmp_v * modules_series
    issues = []
    if not inverter_mppt_min_v <= vmp <= inverter_mppt_max_v:
        issues.append("string Vmp outside inverter MPPT window")
    if voc_cold > inverter_mppt_max_v:
        issues.append("cold Voc exceeds inverter maximum; installer review required")
    return issues
