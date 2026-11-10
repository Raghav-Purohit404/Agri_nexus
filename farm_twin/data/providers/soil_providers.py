"""
FILE: farm_twin/data/providers/soil_providers.py
PURPOSE: Regional soil priors (used ONLY to seed hierarchy levels / fill unmeasured layers as ESTIMATED; never to override a lab report).

IMPLEMENT:
  SoilGridsProvider: ISRIC SoilGrids 2.0 REST (author knowledge, VERIFY): GET https://rest.isric.org/soilgrids/v2.0/properties/query ?lon&lat&property=sand&property=silt&property=clay&property=phh2o&property=soc&property=bdod&property=cec&property=nitrogen&depth=0-5cm&depth=5-15cm&depth=15-30cm&depth=30-60cm&depth=60-100cm&depth=100-200cm&value=mean&value=Q0.05&value=Q0.95
      Returns integer-scaled values with a `d_factor` per property (e.g. clay in g/kg -> /10 = %, phh2o pH*10 -> /10, bdod cg/cm3 -> /100 = g/cm3, soc dg/kg -> /100 = %, cec mmol(c)/kg -> /10 = cmol(c)/kg): READ d_factor and unit_measure from the response; do not hard-code.
      Use Q0.05..Q0.95 to derive uncertainty (sd ~ (Q95-Q05)/3.29). 250 m resolution; known to be weak in arid India and for salinity -> flag "regional_prior_low_confidence_arid".
  IndianSoilHealthProvider: Soil Health Card portal data are not available as a stable open API (VERIFY). Implement a PARSER for the Soil Health Card PDF/CSV the user uploads (see data/ingestion/soil_report.py) and a district-level prior table loader (CSV in data_dir) for N/P/K/OC/pH class distributions.
  GroundwaterProvider: India-WRIS / CGWB groundwater level and quality datasets (station-based, seasonal) loaded from user-supplied downloads; returns depth-to-water, EC, and SAR when available as IMPORTED with station distance.
TESTS: d_factor scaling; uncertainty derivation; prior never overwrites MEASURED.
"""

from __future__ import annotations

from typing import Any

import httpx

from farm_twin.core.provenance import Uncertainty, estimated, missing
from farm_twin.data.providers.base import ProviderKind, ProviderMeta


class SoilGridsProvider:
    meta = ProviderMeta(
        name="soilgrids",
        kind=ProviderKind.SOIL,
        license="CC-BY-4.0",
        attribution_text="ISRIC SoilGrids",
        spatial_res_m=250,
        temporal_res="static map",
        suitable_for_calibration=False,
        suitable_for_validation=False,
        notes="Regional prior; low confidence for arid salinity and small plot scale",
    )
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    properties = ("sand", "silt", "clay", "phh2o", "soc", "bdod", "cec", "nitrogen")
    depths = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")

    def __init__(self, timeout_s: float = 45):
        self.timeout_s = timeout_s

    def parse(self, payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        result = {}
        block = payload.get("properties", {})
        for prop in self.properties:
            rows = []
            for layer in block.get(prop, {}).get("layers", []):
                unit = layer.get("unit_measure", {})
                factor = float(unit.get("d_factor", 1))
                for depth in layer.get("depths", []):
                    vals = depth.get("values", {})
                    mean = vals.get("mean")
                    q05 = vals.get("Q0.05")
                    q95 = vals.get("Q0.95")
                    if mean is None or mean == -9999:
                        continue

                    def scale(v: Any) -> float | None:
                        return None if v is None or v == -9999 else float(v) / factor

                    value = scale(mean)
                    lo = scale(q05)
                    hi = scale(q95)
                    sd = (hi - lo) / 3.29 if lo is not None and hi is not None else None
                    quantified = (
                        estimated(
                            value,
                            str(unit.get("mapped_units", "unknown")),
                            method=f"soilgrids_v2:{prop}",
                            parent_ids=[],
                            uncertainty=Uncertainty(kind="sd", sd=sd),
                        )
                        if sd is not None
                        else missing(str(unit.get("mapped_units", "unknown")), "SoilGrids uncertainty quantiles absent")
                    )
                    rows.append({"depth": depth.get("label"), "value": quantified, "raw_unit": unit})
            result[prop] = rows
        return result

    def fetch_profile(self, lon: float, lat: float) -> dict[str, Any]:
        params = (
            [("lon", lon), ("lat", lat)]
            + [("property", p) for p in self.properties]
            + [("depth", d) for d in self.depths]
            + [("value", v) for v in ("mean", "Q0.05", "Q0.95")]
        )
        response = httpx.get(self.url, params=params, timeout=self.timeout_s)
        response.raise_for_status()
        return {
            "raw": response.json(),
            "estimates": self.parse(response.json()),
            "quality_flags": ["regional_prior_low_confidence_arid"],
        }


class IndianSoilHealthProvider:
    meta = ProviderMeta(
        name="soil_health_card_upload",
        kind=ProviderKind.SOIL,
        license=None,
        temporal_res="soil-test date",
        suitable_for_calibration=True,
        suitable_for_validation=True,
        notes="User-provided laboratory Soil Health Card CSV/PDF; no stable public API assumed",
    )

    def load_csv(self, path: str) -> list[dict[str, Any]]:
        import pandas as pd

        return pd.read_csv(path).to_dict(orient="records")


class GroundwaterProvider:
    meta = ProviderMeta(
        name="user_groundwater_files",
        kind=ProviderKind.WATER,
        license=None,
        temporal_res="station observation",
        suitable_for_calibration=False,
        notes="Offline user-supplied India-WRIS/CGWB data; no fabricated station values",
    )

    def load_csv(self, path: str) -> list[dict[str, Any]]:
        import pandas as pd

        return pd.read_csv(path).to_dict(orient="records")
