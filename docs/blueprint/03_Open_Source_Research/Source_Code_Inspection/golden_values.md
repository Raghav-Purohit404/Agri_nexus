# Golden values generated during blueprint creation
Files: `code_skeleton/tests/golden/`
- aquacrop_tunis_wheat.json - six-season rainfed yields (8.930, 8.393, 9.139, 8.776, 8.710, 8.913 t/ha dry) and irrigated (SMT 70 %) seasonal irrigation (36.0, 85.9, 62.2, 111.0, 50.0, 36.9 mm).
- pvlib_jodhpur_clearsky.json - daily kWh/m2 and kWh for 3 dates.
- wheat_params.json, reference_crop_list.json - dumped from the reference library.
- cvar_milp_prototype.py - runnable CVaR MILP prototype (optimal, HiGHS).
Reproduction: install the reference packages in a throwaway virtualenv; these packages are NEVER runtime dependencies of the product (except optional pvlib cross-check in tests).
Remaining fixture task for Codex (prompt P05): also dump derived values (CGC, CDC, CC0, stage dates, HIGC, tLinSwitch, dHILinear, daily CC and Ks series) for the Tunis wheat run.
