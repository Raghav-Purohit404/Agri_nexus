"""
FILE: farm_twin/gis/terrain.py
PURPOSE: Elevation, slope, aspect for a plot.

IMPLEMENT: fetch_dem(bbox) via provider abstraction (Copernicus GLO-30 or SRTM through data/providers); with rasterio: read window, reproject to local UTM,
    slope/aspect by Horn (1981) 3x3 finite differences:
        dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8*dx); dz/dy = ((g + 2h + i) - (a + 2b + c)) / (8*dy)    (a..i = 3x3 window, a top-left, i bottom-right)
        slope = atan(sqrt(dzdx^2 + dzdy^2)); aspect = atan2(dzdy, -dzdx) converted to compass degrees.
    plot_terrain(polygon) -> (elevation_m, slope_deg, aspect_deg) each Quantified with source=ESTIMATED and uncertainty = DEM vertical RMSE (30 m DEM: state that
    a 100 m2 plot is sub-pixel; a user-measured value (phone clinometer / survey) must override as MEASURED).
TESTS: synthetic plane DEM with known tilt returns the tilt within 0.05 deg.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from farm_twin.core.provenance import Uncertainty, estimated


def horn_slope_aspect(dem: np.ndarray, dx_m: float, dy_m: float) -> tuple[np.ndarray, np.ndarray]:
    if dem.ndim != 2 or min(dem.shape) < 3 or dx_m <= 0 or dy_m <= 0:
        raise ValueError("DEM must be a 2D grid with at least 3x3 cells and positive spacing")
    a, b, c = dem[:-2, :-2], dem[:-2, 1:-1], dem[:-2, 2:]
    d, _, f = dem[1:-1, :-2], dem[1:-1, 1:-1], dem[1:-1, 2:]
    g, h, i = dem[2:, :-2], dem[2:, 1:-1], dem[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * dy_m)
    slope = np.rad2deg(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
    aspect = (np.rad2deg(np.arctan2(dzdy, -dzdx)) + 360) % 360
    return slope, aspect


def plot_terrain(
    dem_window: np.ndarray,
    polygon_pixel_mask: np.ndarray,
    *,
    dx_m: float,
    dy_m: float,
    dem_vertical_rmse_m: float = 4.0,
) -> dict[str, Any]:
    slopes, aspects = horn_slope_aspect(dem_window, dx_m, dy_m)
    mask = polygon_pixel_mask[1:-1, 1:-1]
    elevation = float(np.mean(dem_window[1:-1, 1:-1][mask])) if mask.any() else float(np.mean(dem_window[1:-1, 1:-1]))
    slope = float(np.mean(slopes[mask])) if mask.any() else float(np.mean(slopes))
    aspect = (
        float(np.rad2deg(np.angle(np.mean(np.exp(1j * np.deg2rad(aspects[mask]))))) % 360)
        if mask.any()
        else float(np.mean(aspects))
    )
    method = "DEM_Horn_1981"
    return {
        "elevation_m": estimated(
            elevation, "m", method=method, parent_ids=[], uncertainty=Uncertainty(kind="sd", sd=dem_vertical_rmse_m)
        ),
        "slope_deg": estimated(
            slope, "degree", method=method, parent_ids=[], uncertainty=Uncertainty(kind="sd", sd=1.0)
        ),
        "aspect_deg": estimated(
            aspect, "degree", method=method, parent_ids=[], uncertainty=Uncertainty(kind="sd", sd=10.0)
        ),
        "quality_flags": ["dem_30m_sub_pixel_for_small_plot"],
    }


def fetch_dem(provider: Any, bbox: tuple[float, float, float, float]) -> Any:
    if not hasattr(provider, "fetch_dem"):
        raise NotImplementedError("DEM provider does not implement fetch_dem")
    return provider.fetch_dem(bbox)
