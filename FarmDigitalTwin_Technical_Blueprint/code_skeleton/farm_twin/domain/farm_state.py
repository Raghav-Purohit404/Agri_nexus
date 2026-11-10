"""
FILE: farm_twin/domain/farm_state.py
PURPOSE: THE canonical FarmState. FarmState(t) -> Intervention -> FarmState(t+1).

IMPLEMENT:
    class PlotState: plot (static), soil: SoilState, crop: CropState|None, solar: PVConfig|None, microclimate_adjust (agrivoltaic ground radiation fraction,
        wind factor, dT), land_use, last_observation_dates: dict[var, date]
    class PropertyState: water: WaterState, infra: InfraState, finance: FinancialState
    class FarmState: date, property: PropertyState, plots: dict[PlotId, PlotState], weather_today: WeatherDay(Quantified fields),
        meta: {state_id, parent_state_id, sim_run_id, parameter_set_ids: dict[model, id], created_by}
        methods: snapshot() (deep, immutable-by-convention copy), diff(other) -> list of (path, old, new), hash()
        validate() -> checks invariants: area partition sums to property area (+/-0.5%), theta in [theta_dry, theta_sat], CC in [0,1], carbon pools >= 0,
                      no plot has two incompatible land uses.
    Persist each daily state ONLY as a delta against the previous state (state_delta table) plus periodic full snapshots (monthly); this keeps 10-year x N-scenario runs affordable.
TESTS: snapshot/diff/hash; validate() catches negative carbon pool; delta replay reproduces the state exactly.
"""
