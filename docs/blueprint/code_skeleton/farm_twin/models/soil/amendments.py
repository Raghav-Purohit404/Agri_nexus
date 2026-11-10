"""
FILE: farm_twin/models/soil/amendments.py
PURPOSE: Effects and costing of soil amendments and organic inputs (gypsum, sulphur, lime, FYM, compost, green manure, biochar-flag, mulch).

IMPLEMENT:
 1. Gypsum requirement for sodic soils (derived, unit-checked):
      GR_cmolc_per_kg = CEC_cmolc_kg * (ESP_initial - ESP_target)/100
      gypsum_kg_per_ha = GR_cmolc_per_kg * 8610 * depth_m * bulk_density_t_m3 / purity_fraction / efficiency
        derivation: 1 cmolc/kg exchangeable Na replaced needs 0.5 cmol CaSO4.2H2O (172.17 g/mol -> 0.861 g per kg soil); soil mass per ha = 1e4*depth*BD*1000 kg ; efficiency default 0.75 (flag), purity 0.7-1.0 (user input, product-specific).
      example check: GR=1, depth=0.15 m, BD=1.4 -> 1,808 kg/ha at purity=1, efficiency=1.
      Applicable only if pH_s high and no free CaCO3 requirement conflicts: if CaCO3 > ~1 % and pH>8.5, gypsum still replaces Na but elemental S/acidifier path is a different reaction -> include `recommend_amendment(ph, caco3, esp, ec)` decision table (CSV-driven, editable): sodic (ESP>15, EC<4, pH>8.2) -> gypsum + leaching; saline-sodic -> gypsum then leaching; saline (EC>4, ESP<15) -> leaching only; acid (pH<5.5) -> lime.
 2. Elemental sulphur (pH reduction / S nutrition): conversion 1 kg S -> 4.7 kg gypsum-equivalent Ca release (literature; flag).
 3. Lime requirement (acid soils; unlikely in pilot but implement): buffer-pH-free approximation LR_t_ha = (pH_target - pH)*buffer_capacity(OM, clay)*depth... -> CSV factors flagged placeholder; refuse if buffer data missing.
 4. Organic inputs: FYM/compost/green manure parameters table (dry matter %, C fraction, N, P, K contents, C:N, DPM:RPM:HUM split, mineralisation years) - CSV with provenance (user-measured analysis preferred; defaults literature-flagged). ApplyOrganic -> (a) carbon module inputs (rothc.py), (b) nutrients.py organic N pools, (c) water: improvement of theta_fc/theta_wp via OM change recomputed through pedotransfer each year (OM% updated from carbon module; Ksat/tau recalculated).
 5. Mulch: effect on soil evaporation (fMulch, mulch cover %) and soil temperature (-1 to -3 C optional param); cost items.
 6. Cost & logistics: each amendment returns CostLine(product, quantity, unit_cost, labour_days, application_window).
 7. Safety: dose bounds enforced (gypsum <= 25 t/ha per year, FYM <= 30 t/ha, N <= crop-specific max in crop library); outside bounds -> RangeError with explanation.
TESTS: gypsum formula example above; decision table branches; dose bounds.
"""
