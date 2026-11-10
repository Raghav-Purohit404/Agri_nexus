"""
FILE: farm_twin/gis/plot_geometry.py
PURPOSE: All polygon/CRS handling for plots (use shapely + pyproj + geopandas; do NOT hand-roll geodesy).

IMPLEMENT:
    pick_local_epsg(lon, lat) -> int       # UTM zone: zone = floor((lon+180)/6)+1; EPSG = 32600+zone (N) or 32700+zone (S). Jodhpur (73.02E, 26.24N) -> 32643
    area_m2(polygon_wgs84) -> float        # transform to local UTM, shapely .area
    rect_from_dimensions(length_m, width_m, ref_lonlat, bearing_deg) -> Polygon (WGS84) built in local CRS then transformed back
    polygon_from_vertices_m(vertices_xy_m, ref_lonlat, bearing_deg)
    import_vector(path) -> list[Plot candidates]  (GeoJSON, KML, Shapefile, GeoPackage); reproject to 4326; explode multipolygons; validate
    validate_plot(poly, siblings) -> list[ValidationIssue]  (self-intersection -> try shapely.make_valid and REPORT; overlap; sliver detection)
    shared_boundary_length_m(a,b); centroid_lonlat(poly)
    buffer_inward(poly, metres) -> polygon  (used for edge-effect exclusion zones near trees/walls)
TESTS: 20 ft x 40 ft rectangle -> 74.32 m2 +/- 0.1%; local EPSG for Jodhpur == 32643; KML round trip preserves area within 0.1%.
NOTE: Plots of 55-120 m2 are smaller than one 10 m Sentinel-2 pixel block would like -> see gis/sentinel.py for the mixed-pixel policy.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from pyproj import CRS, Transformer
from shapely import make_valid, ops
from shapely.geometry import Polygon, shape
from shapely.validation import explain_validity


def pick_local_epsg(lon: float, lat: float) -> int:
    zone = min(60, max(1, math.floor((lon + 180) / 6) + 1))
    return (32600 if lat >= 0 else 32700) + zone


def _transformer(src: int, dst: int) -> Transformer:
    return Transformer.from_crs(CRS.from_epsg(src), CRS.from_epsg(dst), always_xy=True)


def area_m2(polygon_wgs84: Polygon) -> float:
    lon, lat = polygon_wgs84.centroid.x, polygon_wgs84.centroid.y
    local = pick_local_epsg(lon, lat)
    transformer = _transformer(4326, local)
    return float(ops.transform(transformer.transform, polygon_wgs84).area)


def rect_from_dimensions(
    length_m: float, width_m: float, ref_lonlat: tuple[float, float], bearing_deg: float = 0
) -> Polygon:
    if length_m <= 0 or width_m <= 0:
        raise ValueError("dimensions must be positive")
    from shapely import affinity

    lon, lat = ref_lonlat
    epsg = pick_local_epsg(lon, lat)
    local = ops.transform(_transformer(4326, epsg).transform, shape({"type": "Point", "coordinates": ref_lonlat}))
    x, y = local.x, local.y
    polygon = Polygon([(x, y), (x + length_m, y), (x + length_m, y + width_m), (x, y + width_m)])
    polygon = affinity.rotate(polygon, 90 - bearing_deg, origin=(x, y), use_radians=False)
    return ops.transform(_transformer(epsg, 4326).transform, polygon)


def polygon_from_vertices_m(
    vertices_xy_m: list[tuple[float, float]], ref_lonlat: tuple[float, float], bearing_deg: float = 0
) -> Polygon:
    from shapely import affinity

    lon, lat = ref_lonlat
    epsg = pick_local_epsg(lon, lat)
    point = ops.transform(_transformer(4326, epsg).transform, shape({"type": "Point", "coordinates": ref_lonlat}))
    polygon = Polygon([(point.x + x, point.y + y) for x, y in vertices_xy_m])
    polygon = affinity.rotate(polygon, 90 - bearing_deg, origin=(point.x, point.y), use_radians=False)
    return ops.transform(_transformer(epsg, 4326).transform, polygon)


def validate_plot(poly: Polygon, siblings: Iterable[Polygon] = ()) -> list[dict[str, Any]]:
    issues = []
    if poly.is_empty:
        return [{"severity": "ERROR", "code": "empty_geometry", "message": "plot has no area"}]
    if not poly.is_valid:
        reason = explain_validity(poly)
        repaired = make_valid(poly)
        issues.append(
            {"severity": "WARN", "code": "invalid_geometry_repaired", "message": reason, "repaired": repaired}
        )
        poly = repaired
    if poly.geom_type != "Polygon":
        issues.append(
            {"severity": "ERROR", "code": "not_polygon", "message": f"expected Polygon, got {poly.geom_type}"}
        )
    if area_m2(poly) < 1:
        issues.append({"severity": "ERROR", "code": "small_plot", "message": "plot area must be at least 1 m2"})
    lon, lat = poly.centroid.x, poly.centroid.y
    epsg = pick_local_epsg(lon, lat)
    trans = _transformer(4326, epsg)
    local = ops.transform(trans.transform, poly)
    for sibling in siblings:
        other = ops.transform(trans.transform, sibling)
        overlap = local.intersection(other).area
        if overlap / max(local.area, 1e-12) > 0.005:
            issues.append({"severity": "ERROR", "code": "plot_overlap", "overlap_m2": overlap})
    return issues


def shared_boundary_length_m(a: Polygon, b: Polygon) -> float:
    lon, lat = a.centroid.x, a.centroid.y
    transformer = _transformer(4326, pick_local_epsg(lon, lat))
    aa = ops.transform(transformer.transform, a)
    bb = ops.transform(transformer.transform, b)
    return float(aa.boundary.intersection(bb.boundary).length)


def centroid_lonlat(poly: Polygon) -> tuple[float, float]:
    point = poly.centroid
    return point.x, point.y


def buffer_inward(poly: Polygon, metres: float) -> Polygon:
    transformer = _transformer(4326, pick_local_epsg(poly.centroid.x, poly.centroid.y))
    inv = _transformer(pick_local_epsg(poly.centroid.x, poly.centroid.y), 4326)
    return ops.transform(inv.transform, ops.transform(transformer.transform, poly).buffer(-metres))


def import_vector(path: str | Path) -> list[Polygon]:
    import geopandas as gpd

    frame = gpd.read_file(path).to_crs(4326)
    out = []
    for geom in frame.geometry:
        if geom is None:
            continue
        geometries = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        out.extend(g for g in geometries if g.geom_type == "Polygon")
    return out
