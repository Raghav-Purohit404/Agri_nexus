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
