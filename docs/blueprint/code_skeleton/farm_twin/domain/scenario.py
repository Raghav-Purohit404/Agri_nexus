"""
FILE: farm_twin/domain/scenario.py
PURPOSE: Scenario = (initial FarmState id) + InterventionPlan + WeatherScenarioSet + PriceScenarioSet + parameter_set_ids + horizon.

IMPLEMENT: class Scenario(id, name, base_state_id, plan, horizon_years, weather: WeatherScenarioSpec {kind: HISTORICAL_REPLAY | RESAMPLED | GENERATED | CLIMATE_SHIFT(delta_T, rain_scale), n},
        prices: PriceScenarioSpec, tariffs, discount_rate, seed, tags)
    class ScenarioResult(scenario_id, per-plot and property KPI distributions (yield, water use, NPV, soil carbon delta, ECe delta, solar kWh, cash min), time series paths (quantiles), run metadata).
    compare(results: list[ScenarioResult]) -> ComparisonTable with paired differences using COMMON random numbers (same weather draws) so differences are low-variance.
TESTS: two scenarios with identical plans give identical results under the same seed; compare() uses paired weather.
"""
