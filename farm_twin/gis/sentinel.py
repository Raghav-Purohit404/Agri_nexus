"""
FILE: farm_twin/gis/sentinel.py
PURPOSE: Satellite vegetation time series per plot (Sentinel-2 L2A) with an honest treatment of tiny plots.

IMPLEMENT:
    search_scenes(polygon, t0, t1, max_cloud=60) -> list[SceneRef]   (via data provider interface; Copernicus Data Space STAC/OData; also allow Planetary Computer / AWS STAC as a swap-in provider)
    read_bands(scene, polygon_buffered) -> arrays for B02,B03,B04,B08,B11 (10 m except B11 20 m resampled), SCL (20 m)
    cloud_mask: valid = SCL in {4 vegetation, 5 bare soil, 6 water, 7 unclassified-low-prob?}  Default: keep {4,5,6}; drop {0,1,3 shadow,8,9 cloud,10 cirrus,11 snow}. Configurable.
    indices:  NDVI = (B08-B04)/(B08+B04);  EVI = 2.5*(B08-B04)/(B08 + 6*B04 - 7.5*B02 + 1);  NDWI = (B03-B08)/(B03+B08);  NDMI = (B08-B11)/(B08+B11); SAVI = 1.5*(B08-B04)/(B08+B04+0.5)
    reflectance scaling: L2A DN / 10000 (apply BOA_ADD_OFFSET if the product metadata declares it - processing baseline >= 04.00 uses -1000; READ the offset from metadata, do not hard-code)
    plot_stats(polygon): MIXED-PIXEL POLICY - a plot of 74 m2 covers < 1 pixel (100 m2). Compute area-weighted mean over pixels intersecting the polygon with weights = intersection area / pixel area;
        report `n_pure_pixels` (pixels with >=95% inside plot) and set quality_flag "sub_pixel_plot" if n_pure_pixels == 0; uncertainty must inflate accordingly. Never present a mixed pixel as plot-pure.
    time-series: regularise to 5-day grid; gap-fill by Savitzky-Golay after linear interpolation OR double-logistic fit (state which); output both raw and smoothed with flags.
    anomaly detection: z-score of NDVI vs the plot's own multi-year phenology envelope (median +/- 1.5 IQR for the same day-of-season); flag drops > 0.15 NDVI within 10 days.
    fcover_from_ndvi(ndvi, ndvi_soil=0.15, ndvi_veg=0.85) = ((ndvi - ndvi_soil)/(ndvi_veg - ndvi_soil))**2 clipped [0,1]  (used to compare satellite cover against model canopy_cover; label ESTIMATED)
TESTS: synthetic bands -> NDVI/EVI exact; cloud mask drops SCL 9; sub-pixel plot flagged; offset read from metadata.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def cloud_mask(scl: np.ndarray, keep_classes: set[int] | None = None) -> np.ndarray:
    return np.isin(scl, list(keep_classes or {4, 5, 6}))


def indices(
    b02: np.ndarray, b03: np.ndarray, b04: np.ndarray, b08: np.ndarray, b11: np.ndarray
) -> dict[str, np.ndarray]:
    ndvi = (b08 - b04) / np.where(np.abs(b08 + b04) > 1e-12, b08 + b04, np.nan)
    evi = (
        2.5
        * (b08 - b04)
        / np.where(np.abs(b08 + 6 * b04 - 7.5 * b02 + 1) > 1e-12, b08 + 6 * b04 - 7.5 * b02 + 1, np.nan)
    )
    ndwi = (b03 - b08) / np.where(np.abs(b03 + b08) > 1e-12, b03 + b08, np.nan)
    ndmi = (b08 - b11) / np.where(np.abs(b08 + b11) > 1e-12, b08 + b11, np.nan)
    savi = 1.5 * (b08 - b04) / np.where(np.abs(b08 + b04 + 0.5) > 1e-12, b08 + b04 + 0.5, np.nan)
    return {"ndvi": ndvi, "evi": evi, "ndwi": ndwi, "ndmi": ndmi, "savi": savi}


def scale_reflectance(
    dn: np.ndarray, *, quantification_value: float = 10000, boa_add_offset: float | None = None
) -> np.ndarray:
    offset = boa_add_offset or 0
    return (dn.astype(float) + offset) / quantification_value


def plot_stats(values: np.ndarray, pixel_geometries: list[Any], polygon: Any) -> dict[str, Any]:
    weights = np.array([g.intersection(polygon).area / g.area for g in pixel_geometries], dtype=float)
    inside = weights > 0
    pure = int(np.sum(weights >= 0.95))
    mean = (
        float(np.average(values[inside], weights=weights[inside]))
        if inside.any() and weights[inside].sum() > 0
        else float("nan")
    )
    std = (
        float(np.sqrt(np.average((values[inside] - mean) ** 2, weights=weights[inside])))
        if inside.any()
        else float("nan")
    )
    return {
        "mean": mean,
        "sd": std,
        "n_pure_pixels": pure,
        "valid_fraction": float(np.mean(inside)),
        "quality_flag": "sub_pixel_plot" if pure == 0 else "ok",
        "pixel_weights": weights.tolist(),
    }


def fcover_from_ndvi(ndvi: float | np.ndarray, ndvi_soil: float = 0.15, ndvi_veg: float = 0.85) -> float | np.ndarray:
    if ndvi_veg <= ndvi_soil:
        raise ValueError("ndvi_veg must exceed ndvi_soil")
    result = np.clip((np.asarray(ndvi) - ndvi_soil) / (ndvi_veg - ndvi_soil), 0, 1) ** 2
    return float(result) if result.ndim == 0 else result


def search_scenes(provider: Any, polygon: Any, t0: Any, t1: Any, max_cloud: float = 60) -> list[Any]:
    if provider is None:
        raise RuntimeError("Sentinel provider is unavailable; no scenes were fabricated")
    return provider.search(polygon, t0, t1, max_cloud=max_cloud)
