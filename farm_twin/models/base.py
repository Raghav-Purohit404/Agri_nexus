"""
FILE: farm_twin/models/base.py
PURPOSE: Domain-facing model interfaces (adapter pattern). The FarmState engine depends ONLY on these Protocols, never on a concrete model.

IMPLEMENT:
  class ModelInfo(BaseModel): name, version, fidelity_level {1,2,3}, supports: set[str] (e.g. {"salinity","nitrogen","co2"}), required_inputs: list[VarSpec], outputs: list[VarSpec], time_step {"daily","monthly","hourly"}, deterministic: bool
  class VarSpec(BaseModel): name, unit, valid_range, kind {MEASURED_OR_ESTIMATED, DERIVED}
  class CropModel(Protocol):    info; validate_inputs(plot_state, weather, plan) -> list[Issue]; init(plot_state, crop_cfg, params) -> CropRunState; step(run_state, weather_day, daily_actions) -> StepResult; run(...) -> RunResult
  class SoilWaterModel(Protocol), SoilCarbonModel(Protocol), SoilNutrientModel(Protocol), SoilSalinityModel(Protocol), SolarModel(Protocol), AgrivoltaicModel(Protocol)
  class StepResult(BaseModel): state_delta, fluxes: dict[str, float] (mm, kg/ha ... in canonical units), diagnostics, warnings
  class ModelRegistry: register(model_cls, info), get(kind, name, version=None); `list_for(kind, crop_id)` returns models that support the crop.
  Capability negotiation: before running, FarmStateEngine asks `info.supports` for every process required by the scenario (e.g. salinity-affected plot requires "salinity"); if the selected crop model lacks it, the engine composes it with the separate salinity model (see state/coupling.py) and records the composition in sim_run.config. NEVER silently ignore a missing process.
RULES: every model run writes (model name, version, parameter_set_id, input_hash) to sim_run; every kernel is pure and numpy-vectorisable over a leading plot/scenario axis.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field


class TimeStep(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    HOURLY = "hourly"


class VariableKind(str, Enum):
    MEASURED_OR_ESTIMATED = "MEASURED_OR_ESTIMATED"
    DERIVED = "DERIVED"


class VarSpec(BaseModel):
    name: str
    unit: str
    valid_range: tuple[float, float] | None = None
    kind: VariableKind = VariableKind.DERIVED


class ModelInfo(BaseModel):
    name: str
    version: str
    fidelity_level: int = Field(ge=1, le=3)
    supports: set[str] = Field(default_factory=set)
    required_inputs: list[VarSpec] = Field(default_factory=list)
    outputs: list[VarSpec] = Field(default_factory=list)
    time_step: TimeStep
    deterministic: bool = True


class Issue(BaseModel):
    code: str
    message: str
    severity: str = "ERROR"


class StepResult(BaseModel):
    state_delta: dict[str, Any]
    fluxes: dict[str, float]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


@runtime_checkable
class ScientificModel(Protocol):
    info: ModelInfo

    def validate_inputs(self, plot_state: Any, weather: Any, plan: Any) -> list[Issue]: ...
    def step(self, run_state: Any, forcing: Any, actions: Any) -> StepResult: ...


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, tuple[type[Any], ModelInfo]] = {}

    def register(self, model_cls: type[Any], info: ModelInfo) -> None:
        key = f"{info.name}@{info.version}"
        if key in self._models:
            raise ValueError(f"model already registered: {key}")
        self._models[key] = (model_cls, info)

    def get(self, kind: str, name: str, version: str | None = None) -> tuple[type[Any], ModelInfo]:
        matches = [
            row
            for row in self._models.values()
            if row[1].name == name and kind in row[1].supports and (version is None or row[1].version == version)
        ]
        if not matches:
            raise KeyError(f"no registered {kind} model named {name}")
        return matches[-1]

    def list_for(self, kind: str, crop_id: str | None = None) -> list[ModelInfo]:
        return [
            info
            for _, info in self._models.values()
            if kind in info.supports and (crop_id is None or crop_id in info.supports)
        ]
