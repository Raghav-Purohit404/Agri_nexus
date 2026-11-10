# Integration registry
| Capability | Chosen approach | Alternative | Why |
|---|---|---|---|
| Crop L1 | native AquaCrop-equivalent engine | wrap reference package | need salinity/N hooks, vectorised scenarios, no runtime dependency |
| Crop L3 | DSSAT subprocess adapter | APSIM | file-based, BSD-3, has millet/sorghum/wheat modules (APSIM not inspected) |
| Soil carbon | native RothC | wrap port | tiny, 5 pools, easy to validate |
| Salinity/N/P/K | native (original) | none exists in L1 engine | required for the arid use case |
| PV chain | native (SPA-grade, Erbs, Perez, PVWatts) | pvlib at runtime | allows custom agrivoltaic coupling; pvlib used as oracle in tests |
| Agrivoltaic ground radiation | original 2-D geometry + brute-force raycast oracle | existing tools | none inspected/licensable; crop response unvalidated |
| Farm records | native PostGIS schema | farmOS | GPL boundary; optional API sync later |
| Optimisation | Pyomo + HiGHS (CP-SAT only for scheduling) | PuLP/OR-Tools | prototype verified |
| Agents | LangGraph + Postgres checkpointer | custom loop | interrupts, retries, persistence |
| GIS | shapely/pyproj/geopandas/rasterio | - | standard |
