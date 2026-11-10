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
