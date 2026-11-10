"""
FILE: farm_twin/data/providers/base.py
PURPOSE: Provider abstraction so no scientific code is tied to one weather/soil/market/satellite vendor.

IMPLEMENT:
    class ProviderMeta(BaseModel): name, kind {WEATHER, SOIL, SATELLITE, MARKET, TARIFF, WATER, DEM}, license, attribution_text, spatial_res_m|None,
        temporal_res, history_start, update_frequency, latency_days, coverage_bbox|None, suitable_for_calibration: bool, suitable_for_validation: bool, notes
    class WeatherProvider(Protocol): fetch_daily(lon, lat, start, end, *, variables) -> WeatherFrame ; fetch_forecast(lon, lat, days) -> WeatherFrame ; meta
    class SoilProvider(Protocol): fetch_profile(lon, lat) -> SoilPrior (per layer mean + uncertainty + sources)
    class MarketProvider(Protocol): fetch_prices(commodity, market, start, end) -> list[PriceObservation]
    class SatelliteProvider(Protocol): search(polygon, t0, t1, max_cloud), read(scene, polygon)
    class TariffProvider(Protocol): get_schedule(state_code, consumer_category, on_date) -> TariffSchedule
    class ProviderRegistry: register(provider), get(kind, name=None), ranked(kind, lon, lat) (picks by coverage, then recency, then user preference)
    ALL providers must: (1) cache raw responses on disk keyed by (provider, request hash) with TTL, store the raw payload as a `dataset` row with sha256;
        (2) return values as Quantified with source=IMPORTED and dataset_id set; (3) never raise on partial data - return MISSING entries + quality_flags;
        (4) implement retry with exponential backoff (3 tries, jitter) and a circuit breaker; (5) work offline from cache when `providers.<name>.enabled=false`.
    WeatherFrame columns (canonical): date, tmax_c, tmin_c, rain_mm, rs_mj_m2, rh_mean_pct|None, tdew_c|None, u2_ms|None, et0_mm|None(provider-computed, NOT trusted over own FAO-56), plus per-column provenance.
    WIND: providers give 10 m wind; convert to 2 m with u2 = u_z * 4.87 / ln(67.8*z - 5.42) (FAO-56 eq. 47).
TESTS: contract tests run each provider against recorded fixtures (vcrpy); missing column -> MISSING not exception; wind conversion u10=3.0 -> u2=2.24 m/s.
"""
