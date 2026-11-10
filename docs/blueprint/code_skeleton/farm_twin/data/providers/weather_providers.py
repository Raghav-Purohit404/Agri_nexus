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
