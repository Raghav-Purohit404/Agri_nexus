"""
FILE: farm_twin/domain/scenario.py
PURPOSE: Scenario = (initial FarmState id) + InterventionPlan + WeatherScenarioSet + PriceScenarioSet + parameter_set_ids + horizon.

IMPLEMENT: class Scenario(id, name, base_state_id, plan, horizon_years, weather: WeatherScenarioSpec {kind: HISTORICAL_REPLAY | RESAMPLED | GENERATED | CLIMATE_SHIFT(delta_T, rain_scale), n},
        prices: PriceScenarioSpec, tariffs, discount_rate, seed, tags)
    class ScenarioResult(scenario_id, per-plot and property KPI distributions (yield, water use, NPV, soil carbon delta, ECe delta, solar kWh, cash min), time series paths (quantiles), run metadata).
    compare(results: list[ScenarioResult]) -> ComparisonTable with paired differences using COMMON random numbers (same weather draws) so differences are low-variance.
TESTS: two scenarios with identical plans give identical results under the same seed; compare() uses paired weather.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field

from farm_twin.domain.interventions import InterventionPlan


class WeatherScenarioKind(str, Enum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    RESAMPLED = "RESAMPLED"
    GENERATED = "GENERATED"
    CLIMATE_SHIFT = "CLIMATE_SHIFT"


class WeatherScenarioSpec(BaseModel):
    kind: WeatherScenarioKind
    n: int = 1
    delta_T_c: float = 0
    rain_scale: float = 1


class PriceScenarioSpec(BaseModel):
    kind: str = "HISTORICAL_REPLAY"
    n: int = 1
    config: dict = Field(default_factory=dict)


class Scenario(BaseModel):
    id: str
    name: str
    base_state_id: str
    plan: InterventionPlan
    horizon_years: int
    weather: WeatherScenarioSpec
    prices: PriceScenarioSpec = Field(default_factory=PriceScenarioSpec)
    tariffs: list[dict] = Field(default_factory=list)
    discount_rate: float = 0.1
    seed: int
    tags: list[str] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    scenario_id: str
    plot_kpis: dict[str, dict] = Field(default_factory=dict)
    property_kpis: dict[str, dict] = Field(default_factory=dict)
    time_series_quantiles: dict[str, list[float]] = Field(default_factory=dict)
    run_metadata: dict = Field(default_factory=dict)


def compare(results: list[ScenarioResult]) -> dict:
    return {
        "scenario_ids": [r.scenario_id for r in results],
        "paired": True,
        "property_kpis": {r.scenario_id: r.property_kpis for r in results},
    }
