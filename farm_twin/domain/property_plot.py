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

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from farm_twin.core.ids import new_id
from farm_twin.core.provenance import Quantified


class LandUse(str, Enum):
    CROPLAND = "CROPLAND"
    FALLOW = "FALLOW"
    PV_GROUND = "PV_GROUND"
    AGRIVOLTAIC = "AGRIVOLTAIC"
    WATER_STORAGE = "WATER_STORAGE"
    STRUCTURE = "STRUCTURE"
    OTHER = "OTHER"


class Property(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: new_id("property"))
    name: str
    country_iso: str
    region_code: str | None = None
    climate_zone: str | None = None
    tz: str = "Asia/Kolkata"
    reference_point: tuple[float, float]
    crs_local_epsg: int | None = None
    land_unit_factors: dict[str, float] = Field(default_factory=dict)
    currency: str = "INR"
    plots: list[str] = Field(default_factory=list)
    area_m2: float | None = None


class Plot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: new_id("plot"))
    property_id: str
    name: str
    geometry: Any
    area_m2: float
    perimeter_m: float | None = None
    centroid: tuple[float, float] | None = None
    elevation_m: Quantified[float] | None = None
    slope_deg: Quantified[float] | None = None
    aspect_deg: Quantified[float] | None = None
    land_use_current: LandUse = LandUse.CROPLAND
    neighbours: list[tuple[str, float]] = Field(default_factory=list)
    eligible_uses: set[LandUse] = Field(default_factory=lambda: {LandUse.CROPLAND, LandUse.FALLOW})

    @field_validator("area_m2")
    @classmethod
    def positive_area(cls, value: float) -> float:
        if value < 1:
            raise ValueError("plot area must be at least 1 m2")
        return value
