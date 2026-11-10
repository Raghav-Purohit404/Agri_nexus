# Source inspection log (what was actually done)

Date of inspection: 2026-11-07. Shallow clones (depth 1) in a sandbox; packages installed and run where noted.

| Project | Commit / version | Licence (read from LICENSE file) | Inspected how | Depth |
|---|---|---|---|---|
| AquaCrop-OSPy | b0560c4 (2026-09-23), pkg 3.1.0 | Apache-2.0 | cloned, installed, RUN on bundled Tunis wheat; read daily loop, canopy, water stress, biomass, HI, drainage, runoff, soil evaporation, root growth, soil PTFs, HIGC/linear-HI | deep |
| pvlib-python | c5de586 (2026-11-03), pkg 0.16.1 | BSD-3-Clause | cloned, installed, RUN (clear-sky Jodhpur PVWatts chain); listed public functions of solarposition, irradiance, temperature, pvsystem, inverter, tracking, shading, bifacial | medium |
| DSSAT-CSM-OS | 25c93b9 (2026-10-02) | BSD-3-Clause (DSSAT Foundation) | cloned; read directory structure, module list, genotype files; NOT read equations | structure only |
| farmOS | 414a671 (2026-11-05) | **GPL-2.0** | cloned; read data-model docs (asset/log/quantity types), module list (land assets, lab_test logs: soil/tissue/water, test quantities) | structure + docs |
| LangGraph | e5e37b5 (2026-11-06), wheel 1.2.x | MIT | cloned; confirmed primitives StateGraph, interrupt, Command, Send, RetryPolicy, checkpoint packages (postgres/sqlite) | API surface |
| pyRothC | 5a8f2e2 (2024-01-30) | CC0-1.0 | cloned; read the whole 342-line implementation | deep |
| Pyomo 6.10.1 + HiGHS | pip | (library) | RUN: CVaR MILP prototype solved to optimality via `appsi_highs` | prototype |
| APSIM / ApsimX | - | - | NOT inspected | none |
| Agrivoltaic tools (NREL InSPIRE, aiana GPL-3, etc.) | - | mixed/NOASSERTION/GPL | listed via GitHub search only; code NOT read | none |

## Verified findings that changed the design
1. AquaCrop-OSPy has **no salinity, no soil-fertility (N/P/K), no weed, no perennial/regrowth** support (README + code grep) -> salinity.py and nutrients.py are original specs.
2. Reference crop library lacks pearl millet, mustard, chickpea, cluster bean, cumin, groundnut, sesame, castor -> placeholder-parameter policy + calibration; DSSAT has a CERES-Millet module directory (Level-3 cross-check path).
3. Reference crop params use **-9.0 sentinels** meaning "derive at run time" -> must not be read as numbers.
4. AquaCrop soil: drainage characteristic `tau = round(0.0866*Ksat^0.35, 2)` clamped [0,1]; evaporation defaults (Kex 1.1, fevap 4, fWrelExp 0.4, fwcc 50, REW 9, EvapZmin 0.15, EvapZmax 0.30, zCN 0.3).
5. pyRothC constants verified (k = 10, 0.3, 0.66, 0.02; x = 1.67(1.85+1.60 e^(-0.0786 clay)); partition 0.46/(x+1), 0.54/(x+1)); its code **does not apply the 0.6 vegetation-cover factor** -> specified as configurable switch default ON (documented decision required).
6. farmOS is GPL-2.0 -> integrate only across the REST/JSON:API boundary or by data export/import; never copy its code.
7. CVaR (Rockafellar-Uryasev) MILP in Pyomo/HiGHS works as specified.

## Not verified (must be checked by Codex)
- All external data endpoints (Open-Meteo, NASA POWER, SoilGrids, Agmarknet, IMD) - sandbox egress was restricted.
- Literature constants flagged "UNVERIFIED" in the skeleton (IOM equation, salt tolerance a/b values, Justes N dilution, Brandemuehl-Beckman effective angles, TDS factors, Suarez adjustments).
- DSSAT input-file formats and module codes for the Indian crops.
