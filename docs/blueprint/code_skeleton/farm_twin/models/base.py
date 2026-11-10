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
