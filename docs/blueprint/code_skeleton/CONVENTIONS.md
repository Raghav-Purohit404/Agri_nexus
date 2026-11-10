# GLOBAL CONVENTIONS (every module MUST obey; Codex: read before touching any file)

## Units (canonical, internal)
| Quantity | Unit | Notes |
|---|---|---|
| length (soil depth, root depth) | m | water depths in **mm** |
| water depth / flux | mm, mm/day | 1 mm over 1 m2 = 1 L |
| volumetric water content | m3/m3 | theta, never percent internally |
| temperature | degC | |
| radiation | MJ/m2/day (daily), W/m2 (hourly) | PAR = umol/m2/s or MJ/m2/day, state which |
| area | m2 (plots are small: 600-1300 sq ft = 55.7-120.8 m2) | 1 sq ft = 0.09290304 m2 |
| yield / biomass | t/ha (kg/ha for nutrients) | convert at I/O boundary only |
| soil carbon | t C/ha (to depth of layer), % for lab input | |
| money | INR (float, nominal) | store currency code on every cashflow |
| energy | kWh | power kW |
| EC | dS/m, ESP in %, SAR in (mmol/L)^0.5 | |

## Time
* Crop + soil-water + salinity + nutrient models: **daily** step, UTC date, no sub-daily state.
* RothC: **monthly** step. Solar: **hourly**. Finance: **annual** (monthly optional).
* Use `datetime.date` for daily, tz-aware `pandas.Timestamp` for hourly. Local tz for India = Asia/Kolkata.

## Provenance rule (NON-NEGOTIABLE)
Every scalar or series that enters FarmState is wrapped in `core.provenance.Quantified`
with `source` in {MEASURED, IMPORTED, ESTIMATED, MODEL_PREDICTED, MISSING}. Code must NEVER:
* upgrade ESTIMATED/MODEL_PREDICTED to MEASURED,
* fill a MISSING value silently (it may fill with an ESTIMATED value that carries `method` + `uncertainty`),
* write MODEL_PREDICTED into the observation tables.

## Style
Python 3.11, type hints everywhere, pydantic v2 models for all I/O contracts, numpy vectorised where
a plot-batch dimension exists, pure functions for scientific kernels (no I/O, no globals), dataclasses
or pydantic for state. Every scientific kernel has a docstring citing the equation in THIS repo's docs,
unit-annotated parameters (`x_mm`, `theta_m3m3`), and a unit test with a hand-computed value.

## Determinism
Every stochastic function accepts `rng: numpy.random.Generator`. No global seeds. Simulation runs record
(model_version, parameter_set_id, input_hash, rng_seed, config_json) in `sim_run` table.

## Errors
Raise subclasses of `core.errors.FarmTwinError`. Never `except Exception: pass`. Scientific kernels raise
`UnitError`, `RangeError`, `MassBalanceError`; tools catch them and return structured failure objects.
