# MODEL FIDELITY MATRIX
Levels: L1 simple/native, L2 enhanced (needs data), L3 detailed external cross-check. Status: VERIFIED-REF = reproduces reference output in golden test; SPEC = specified, not yet validated; EXPERIMENTAL = no validated reference.

| Process | L1 (default) | L2 | L3 | Status of L1 | Key limits |
|---|---|---|---|---|---|
| Reference ET0 | FAO-56 PM daily (Hargreaves fallback) | - | - | SPEC (test vs FAO-56 worked example) | needs RH/wind or accepts lower confidence |
| Soil hydraulics | Saxton-Rawls-type PTF + uncertainty | measured WP/FC/Ksat | Richards eq. (van Genuchten) | SPEC (PTF forms from reference source) | Ksat uncertain by orders of magnitude |
| Soil water balance | layered tipping bucket, tau drainage, CN runoff, 2-stage Es | + capillary rise/water table | Richards | VERIFIED-REF via crop golden | no preferential flow, no lateral flow |
| Crop growth | water-driven canopy-cover model | + light limitation (RUE) | DSSAT process model | VERIFIED-REF (wheat only) | placeholder params for most Indian crops |
| Phenology | GDD or calendar | - | DSSAT | SPEC | stress delay approximated |
| Salinity | layered salt mass balance + Maas-Hoffman | + ion/SAR equilibrium | - | SPEC, unvalidated locally | no precipitation/dissolution at L1 |
| Sodicity | SAR->ESP empirical, Ksat reduction | - | - | SPEC | empirical |
| Nitrogen | simple pools + RothC-linked mineralisation | calibrated rates | DSSAT soil N | SPEC (priors) | denitrification very uncertain |
| P, K | empirical response | - | DSSAT P/K | SPEC | index-based |
| Soil carbon | RothC 5 pools monthly | + daily moisture driver | - | SPEC (constants VERIFIED) | topsoil only; pool split estimated |
| PV energy | SPA-grade + Erbs + Perez + PVWatts | + bifacial view factors | pvlib oracle in tests | SPEC + golden | clear-sky golden only |
| Agrivoltaic radiation | 2-D geometry, isotropic diffuse | anisotropic sky, finite rows | ray-trace oracle | SPEC (oracle test) | finite-row end effects ignored |
| Agrivoltaic crop response | ET0 shading + RUE light cap | shade-adaptive terms | - | EXPERIMENTAL | no validated crop response |
| Finance | DCF, tariffs, CVaR | - | - | SPEC | no hard-coded prices/tariffs |
| Uncertainty | weather replay/generator x posterior x prices | - | - | SPEC | needs long records for generator |
| Optimisation | MILP CVaR (Pyomo/HiGHS) | multi-year rolling | - | PROTOTYPED | linearity relies on precomputed payoffs |
| Calibration | hierarchical Bayes + gate | ML residual (>=30 outcomes) | - | SPEC | few observations -> mostly priors |

Reporting rule: every report prints the level and status used per process, plus any EXPERIMENTAL or placeholder flags.
