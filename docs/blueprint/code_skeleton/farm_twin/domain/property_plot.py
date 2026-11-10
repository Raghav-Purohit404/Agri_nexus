"""
FILE: farm_twin/domain/property_plot.py
PURPOSE: Property and Plot entities (the spatial skeleton of the twin). Plots may be any size/shape (the pilot has
800, 600 and 1300 sq ft plots) so NOTHING may assume hectare-scale fields or rectangular geometry.

IMPLEMENT pydantic models:
    Property: id, name, country_iso, region_code (e.g. "IN-RJ"), climate_zone (Koppen code, estimated), tz,
              reference_point (lon,lat WGS84), crs_local_epsg (UTM zone auto-picked from centroid, e.g. 32643 for Jodhpur),
              land_unit_factors: dict[str,float]  (bigha etc., per property), currency="INR", plots: list[PlotId]
    Plot: id, property_id, name, geometry (Shapely Polygon in WGS84; stored as PostGIS geometry(Polygon,4326)),
          area_m2 (computed in local CRS, NEVER from degrees), perimeter_m, centroid, elevation_m: Quantified,
          slope_deg: Quantified, aspect_deg: Quantified, land_use_current (enum: CROPLAND, FALLOW, PV_GROUND, AGRIVOLTAIC,
          WATER_STORAGE, STRUCTURE, OTHER), neighbours: list[(PlotId, shared_boundary_m)],
          eligible_uses: set[LandUse] (user constraints, e.g. Plot C allowed {PV_GROUND, AGRIVOLTAIC, FALLOW})
    PlotValidationRules: polygon valid & simple, area within +/-2% of user-entered dimension if both given (else warn),
          no overlap > 0.5% area with sibling plots (shapely intersection in local CRS), min area 1 m2.
    Entry modes: (a) draw on map -> GeoJSON, (b) import GeoJSON/KML/shapefile/GeoPackage, (c) enter dimensions
          (rect L x W, or vertex list in metres relative to a reference corner + bearing) -> geometry via gis.plot_geometry.
TESTS: 800 sq ft rectangle 20 ft x 40 ft -> area_m2 within 0.1% of 74.322; overlap detection; invalid bow-tie polygon rejected.
"""
