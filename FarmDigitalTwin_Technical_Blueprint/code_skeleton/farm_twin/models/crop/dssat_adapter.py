"""
FILE: farm_twin/models/crop/dssat_adapter.py
PURPOSE: OPTIONAL Level-3 cross-validation engine: run a detailed process crop model (DSSAT-CSM, external executable, BSD-3) as a subprocess for crops where it has a dedicated module, and compare to Level 1. NEVER required for the core pipeline.

IMPLEMENT (adapter pattern, behind `CropModel` protocol):
   locate_executable(): env DSSAT_EXE or `dscsm048`; if absent -> adapter reports unavailable (tests skipped, UI hides Level 3).
   write_inputs(workdir, plot_state, weather, crop_cfg, plan): produce the DSSAT text inputs - weather file (.WTH: DATE, SRAD MJ/m2/d, TMAX, TMIN, RAIN, optional DEWP/WIND/PAR), soil file (.SOL: layer boundaries cm, LL, DUL, SAT, SRGF, SSAT, BD, OC, clay/silt/sand, pH, CEC...), experiment file (FILEX: treatments, planting date, population, row spacing, irrigation events/auto-irrigation rules, fertiliser events, initial conditions), plus a batch file; each file has fixed-column formats -> CODEX MUST read the DSSAT format documentation at implementation time (not reproduced here) and add a round-trip test using the model's own sample inputs.
   run(workdir, module_code, timeout_s) -> parse summary output (Summary.OUT: yield (HWAM, kg/ha), maturity, biomass (CWAM), N uptake, season irrigation) and PlantGro.OUT (daily LAI, biomass, stress factors) into DailyOutput-compatible frames.
   Module codes available in the source tree include dedicated models for: pearl millet (CERES-Millet), sorghum, wheat/barley (CERES and NWheat variants), maize, rice, potato, cassava, sugarcane, sunflower and the CROPGRO legume family (grain legumes, cotton, canola-type) - confirm exact module codes and cultivar-file coverage for the Indian crops of interest at implementation time (file listing of the model data directory); mark crops lacking a cultivar record as unsupported.
   Differences to document: DSSAT is light/temperature/N-driven with explicit LAI, N and (optionally) P/K; Level 1 is water-driven with canopy cover. Compare via `crop/cross_check.py`: yield difference, phenology dates, seasonal water use; report agreement bands; DISAGREEMENT > 25 % yield triggers a Validation Agent flag - not an automatic switch of engine.
   Licensing: external process, no code vendoring; keep invocation isolated in a container image `docker/dssat.Dockerfile` (Codex: build from the upstream repository tag at image build time).
TESTS: skipped when exe missing; with exe present: run the model's shipped example, parse yield, assert plausible range and unit conversion (kg/ha -> t/ha).
"""
