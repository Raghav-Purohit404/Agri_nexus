# Model decisions and limitations

| Area | Current decision | Fidelity / status | Evidence or unresolved work |
|---|---|---|---|
| Provenance | Each data observation carries MEASURED, IMPORTED, ESTIMATED, MODEL_PREDICTED or MISSING; derivations cannot be relabeled measurements. | Contract implemented, runtime unverified | Requires tests and DB enforcement validation. |
| ET0 | FAO-56 Penman–Monteith is the primary method; Hargreaves is an explicitly identified fallback. | Essential method coded; unverified in runtime | Needs supplied fixture and hand-calculated test. |
| Soil water | Daily bucket and curve-number runoff kernel preserve explicit units. | Partial | Full blueprint process order, surface/bund storage, capillary rise, and layered constraints remain incomplete. |
| Crop | AquaCrop-inspired modular kernels; wheat is the only intended configured fixture crop. | Partial/unvalidated | Fixture supplies limited output values; daily arrays and derivation data are absent. Other crop entries remain placeholders. No AquaCrop parity claim. |
| Pedotransfer | Saxton–Rawls estimate retained with uncertainty. | Estimated, not measured | Local measured hydraulic data required for calibration. |
| RothC | Five-pool carbon ledger with explicit inputs and losses. | Research model coded, unverified | RothC initialization and environmental modifiers need reference fixtures; IOM shortcut/constant is unverified. |
| Nutrients | Separate transformation, uptake, and leaching kernels. | Partial | No full daily coupled ledger or site-specific parameterization. |
| Salinity | L1 empirical salt mass transport; outputs labeled locally unvalidated. | Empirical/unvalidated | TDS conversion (640/800), EC1:5 factor, ESP relation, sodicity reduction, and Suarez adjustment need locally supported evidence/calibration. No precipitation/ion exchange. |
| Crop salt response | FAO threshold inputs are not silently inferred when unknown. | Literature-derived inputs | FAO table values do not establish a farm-specific yield response. |
| Solar | Solar position, transposition, temperature, and PV power pathway implemented as a kernel. | L1 coded; golden untested | Validate against pvlib and Jodhpur fixture; local weather, module, inverter, albedo, soiling and loss assumptions unresolved. |
| Agrivoltaics | Geometry/radiation separated from crop coupling. | Experimental research extension | Isotropic diffuse approximation and crop-response factors require measurement; no scientific validation claim. |
| Finance | Deterministic calculations consume explicit scenario assumptions; no price/tariff defaults presented as local facts. | Partial | Need textbook tests; tax, tariff rules, price basis and local cost data are user-configured. |
| Provider integrations | Open-Meteo, NASA POWER, SoilGrids and configured market inputs have adapters/contracts. | Not operationally tested | No response payloads fabricated. Agmarknet resource ID/schema and credentials require configuration. |

## Open scientific assumptions

The blueprint itself labels several empirical constants as placeholders. Keep those labels attached to model outputs. In particular, do not treat the RothC inert organic matter shortcut, salinity conversions, crop-specific parameter placeholders, PV performance defaults, or agrivoltaic yield response as experimentally established. Record parameter source, version, uncertainty, and calibration evidence before deployment.

## P09–P16 implementation decisions

- The P09 engine is dependency-injected and requires explicit transition functions. It does not silently call models that lack a registered composition. Hindcast consumes actual interventions supplied in each forcing record.
- Event dispatch and the feedback ledger are process-local foundations; exactly-once/durable behavior requires the PostgreSQL outbox and persistence implementation.
- The P10 block bootstrap accepts year-block resampling only. Markov/gamma weather synthesis was not added because distribution parameters must be fit to real observed station data and no station dataset is present.
- P11 ensemble MCMC uses an injected log-posterior and fixed random seed; its basic R-hat/ESS diagnostics only indicate chain behavior, not identifiability or model adequacy. The ABC implementation is quantile rejection, not importance-corrected ABC-SMC. Neither sampler can promote parameters without independent predictive evaluation.
- P11 residual learning fits the physical-model residual using shallow LightGBM, preserves input chronology for a blocked calibration tail (or sorts supplied dates), and exposes only a candidate. Minimum 30 outcomes is a floor, not evidence of adequacy; conformal coverage remains marginal and must be evaluated against independent seasons. Text model artifact plus JSON manifest uses a hash; artifacts still require trusted directory and access controls.
- The P12 enumerator computes exact choices only under a bounded combination count. It raises when the cap is exceeded instead of implying a scalable MILP result.
- P14 approval authority and audit buffer are process-local. Production policy requires durable one-time token consumption and append-only database audit, both currently incomplete.
- P15 API/worker runtime entry points require explicit Python service factories. The default API is health/OpenAPI-only and protected operations return unavailable; this prevents accidental unauthenticated deployment but means a deployment adapter is still required. The quality route reports no completeness score until requirements are registered per model.
- State persistence stores JSON key operations between snapshots and treats arrays as replaced values; it is not a general RFC 6902 implementation. Validate replay equivalence against FarmState fixtures before using it for long histories.
- Pyomo CVaR/chance-constrained models and non-contiguous feasible option handling are implemented as solver formulations but remain numerically unverified; mathematical optimization output must not be used for farm decisions until regression and solver comparison tests pass.
