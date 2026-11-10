"""
FILE: farm_twin/data/providers/weather_providers.py
PURPOSE: Concrete weather providers. ENDPOINT FACTS BELOW ARE FROM AUTHOR KNOWLEDGE and were NOT verified live (sandbox egress was limited):
         Codex MUST verify each endpoint, parameter name and unit against the provider's live metadata before relying on it, and record the verification in docs/provider_verification.md.

IMPLEMENT classes:
  OpenMeteoProvider
     archive:  GET https://archive-api.open-meteo.com/v1/archive  ?latitude&longitude&start_date&end_date&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,shortwave_radiation_sum,wind_speed_10m_max (or mean),relative_humidity_2m_mean,et0_fao_evapotranspiration &timezone=Asia/Kolkata
     forecast: GET https://api.open-meteo.com/v1/forecast with same daily vars (+ forecast_days up to 16)
     Notes: shortwave_radiation_sum is MJ/m2 per day (verify); reanalysis-based (ERA5-family) -> coarse (~10-25 km): NOT a measurement at the plot -> source=IMPORTED, flag "gridded_reanalysis".
  NasaPowerProvider
     GET https://power.larc.nasa.gov/api/temporal/daily/point ?parameters=T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN,RH2M,WS2M &community=AG &longitude &latitude &start=YYYYMMDD &end=YYYYMMDD &format=JSON
     Missing values are encoded as -999 -> convert to MISSING. Read the units from the response `parameters` block; do not hard-code radiation units.
     Long record (1981-present) -> primary source for climatology and weather-generator fitting.
  ImdProvider
     IMD gridded rainfall (0.25 deg) and temperature (1 deg) are distributed as binary GRD / NetCDF via the IMD Pune data portal (registration/download workflow, no stable public REST - VERIFY).
     Implement a FILE-BASED loader: user (or an offline script) places the files in data_dir/imd/; the loader reads them with xarray, extracts the grid cell(s), returns WeatherFrame. Treat as best rainfall source for India for calibration/validation.
  StationProvider (user's own weather station / CSV upload): highest trust; source=MEASURED; accepts CSV with a column-mapping UI.
  WeatherBlender: merge sources per variable with priority MEASURED station > IMD (rain) > NASA POWER/Open-Meteo; output includes a `source_used` column; compute bias vs station when overlapping (monthly multiplicative for rain, additive for temperature) and expose bias-correction as ESTIMATED with uncertainty.
TESTS: recorded-fixture tests; -999 -> MISSING; blender picks station over gridded; bias correction preserves monthly mean of the target.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from farm_twin.core.provenance import imported, missing
from farm_twin.data.providers.base import ProviderKind, ProviderMeta, WeatherFrame


class OpenMeteoProvider:
    """Operational archive/forecast adapter; gridded weather remains IMPORTED, never MEASURED."""

    meta = ProviderMeta(
        name="open_meteo",
        kind=ProviderKind.WEATHER,
        license="CC-BY-4.0",
        attribution_text="Open-Meteo, based on cited meteorological datasets",
        spatial_res_m=10000,
        temporal_res="daily",
        suitable_for_calibration=False,
        suitable_for_validation=False,
        notes="Reanalysis/forecast grid; not a plot-level measurement",
    )
    archive_url = "https://archive-api.open-meteo.com/v1/archive"
    forecast_url = "https://api.open-meteo.com/v1/forecast"
    daily_vars = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "shortwave_radiation_sum",
        "wind_speed_10m_max",
        "relative_humidity_2m_mean",
    ]

    def __init__(self, timeout_s: float = 30):
        self.timeout_s = timeout_s

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = httpx.get(url, params=params, timeout=self.timeout_s)
        response.raise_for_status()
        return response.json()

    def _frame(self, payload: dict[str, Any]) -> WeatherFrame:
        daily = payload.get("daily", {})
        times = daily.get("time", [])
        rows = []
        provenance = {}
        names = {
            "temperature_2m_max": "tmax_c",
            "temperature_2m_min": "tmin_c",
            "precipitation_sum": "rain_mm",
            "shortwave_radiation_sum": "rs_mj_m2",
            "wind_speed_10m_max": "u10_ms",
            "relative_humidity_2m_mean": "rh_mean_pct",
        }
        for i, stamp in enumerate(times):
            row = {"date": date.fromisoformat(stamp)}
            for source, name in names.items():
                vals = daily.get(source)
                value = vals[i] if vals and i < len(vals) else None
                row[name] = value
                provenance.setdefault(name, []).append(
                    imported(
                        value,
                        "mm"
                        if name == "rain_mm"
                        else "MJ/m^2/day"
                        if name == "rs_mj_m2"
                        else "degC"
                        if name.endswith("_c")
                        else "%"
                        if name == "rh_mean_pct"
                        else "m/s",
                        method="open-meteo-reanalysis" if "generationtime_ms" in payload else "open-meteo",
                        quality_flags=["gridded_reanalysis"],
                    )
                ) if value is not None else provenance.setdefault(name, []).append(
                    missing("unknown", "provider value missing")
                )
            if row.get("u10_ms") is not None:
                row["u2_ms"] = row["u10_ms"] * 4.87 / __import__("math").log(67.8 * 10 - 5.42)
            rows.append(row)
        return WeatherFrame(rows=rows, provenance=provenance, quality_flags=["gridded_reanalysis"])

    def fetch_daily(
        self, lon: float, lat: float, start: date, end: date, *, variables: list[str] | None = None
    ) -> WeatherFrame:
        payload = self._request(
            self.archive_url,
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": ",".join(variables or self.daily_vars),
                "timezone": "Asia/Kolkata",
            },
        )
        return self._frame(payload)

    def fetch_forecast(self, lon: float, lat: float, days: int) -> WeatherFrame:
        payload = self._request(
            self.forecast_url,
            {
                "latitude": lat,
                "longitude": lon,
                "forecast_days": days,
                "daily": ",".join(self.daily_vars),
                "timezone": "Asia/Kolkata",
            },
        )
        return self._frame(payload)


class NasaPowerProvider:
    meta = ProviderMeta(
        name="nasa_power",
        kind=ProviderKind.WEATHER,
        license="NASA POWER data use policy",
        attribution_text="NASA POWER",
        spatial_res_m=50000,
        temporal_res="daily",
        history_start=date(1981, 1, 1),
        suitable_for_calibration=True,
        suitable_for_validation=False,
        notes="Satellite/reanalysis data are gridded, not plot measurements",
    )
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    parameters = {
        "T2M_MAX": "tmax_c",
        "T2M_MIN": "tmin_c",
        "PRECTOTCORR": "rain_mm",
        "ALLSKY_SFC_SW_DWN": "rs_mj_m2",
        "RH2M": "rh_mean_pct",
        "WS10M": "u10_ms",
    }

    def __init__(self, timeout_s: float = 60):
        self.timeout_s = timeout_s

    def fetch_daily(
        self, lon: float, lat: float, start: date, end: date, *, variables: list[str] | None = None
    ) -> WeatherFrame:
        response = httpx.get(
            self.url,
            params={
                "parameters": ",".join(self.parameters),
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
                "time-standard": "UTC",
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
        block = payload.get("properties", {}).get("parameter", {})
        units = payload.get("parameters", {})
        rows_by_day: dict[str, dict[str, Any]] = {}
        prov = {}
        for key, name in self.parameters.items():
            series = block.get(key, {})
            unit = (units.get(key) or {}).get("units")
            for stamp, raw in series.items():
                row = rows_by_day.setdefault(stamp, {"date": date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))})
                val = None if raw is None or float(raw) == -999 else float(raw)
                if val is not None and name == "rs_mj_m2" and unit and "kWh" in unit:
                    val *= 3.6
                row[name] = val
                q = (
                    imported(
                        val,
                        "MJ/m^2/day"
                        if name == "rs_mj_m2"
                        else "mm"
                        if name == "rain_mm"
                        else "degC"
                        if name.endswith("_c")
                        else "%"
                        if name == "rh_mean_pct"
                        else "m/s",
                        method="nasa-power-daily",
                        quality_flags=["gridded_reanalysis", f"provider_unit:{unit or 'unknown'}"],
                    )
                    if val is not None
                    else missing("unknown", "NASA POWER missing sentinel")
                )
                prov.setdefault(name, []).append(q)
        for row in rows_by_day.values():
            if row.get("u10_ms") is not None:
                row["u2_ms"] = row["u10_ms"] * 4.87 / __import__("math").log(67.8 * 10 - 5.42)
        return WeatherFrame(
            rows=sorted(rows_by_day.values(), key=lambda r: r["date"]),
            provenance=prov,
            quality_flags=["gridded_reanalysis"],
            dataset_id=None,
        )

    def fetch_forecast(self, *args: Any, **kwargs: Any) -> WeatherFrame:
        raise NotImplementedError("NASA POWER does not expose the forecast provider contract")
