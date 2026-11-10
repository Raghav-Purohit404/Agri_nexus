# Build order (each step has acceptance tests)
P00 scaffold/CI -> P01 core+domain -> P02 DB+repos -> P03 GIS+providers+ingestion+quality -> P04 ET0+pedotransfer+water balance -> P05 crop engine (golden fixtures first) -> P06 salinity+nutrients+RothC+amendments -> P07 solar+agrivoltaic -> P08 finance -> P09 state engine -> P10 uncertainty -> P11 calibration+gate+ML -> P12 optimisation+VOI -> P13 feedback loop -> P14 tool layer+agents -> P15 API+UI -> P16 hardening+evals.
Do not start a step until previous acceptance tests pass.
