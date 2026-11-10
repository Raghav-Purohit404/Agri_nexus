"""
FILE: farm_twin/models/soil/water_balance.py
PURPOSE: Daily multi-layer soil-water balance (the physical core shared by crop, salinity and nutrient models). Level 1 = layered tipping-bucket with the processes below, executed in this EXACT order each day (order matters for mass balance):

  1. groundwater table check (adjust theta_fc in saturated zone) [if water table present]
  2. root development (from the crop model; Zr)
  3. drainage (redistribution below field capacity)
  4. surface runoff + infiltration partitioning (curve number)
  5. irrigation (applied depth, efficiency, wetted-surface fraction)
  6. infiltration into layers with Ksat cap, surface storage / ponding
  7. capillary rise from water table
  8. soil evaporation (two-stage, REW)
  9. crop transpiration extraction (root-weighted sink, stress-limited)  [needs crop model's Tr demand]
 10. groundwater inflow
 -> compute stress coefficients for next day; write ledger; assert mass balance.

EQUATIONS:
 (a) Drainage per layer i (tau_i from pedotransfer, theta_fcAdj = FC unless water table):
       if theta <= theta_fcAdj: dTh = 0
       elif theta >= theta_sat: dTh = tau*(theta_sat - theta_fc)
       else: dTh = tau*(theta_sat - theta_fc)*(exp(theta - theta_fc) - 1)/(exp(theta_sat - theta_fc) - 1)
       dTh limited so theta - dTh >= theta_fcAdj; flux out = dTh*dz*1000 [mm]
       Process layers top->bottom: the drained water from layer i enters layer i+1; layer i+1 can accept at most up to theta_sat (excess is held back in layer i);
       the flux between layers is capped by Ksat of the receiving layer; the bottom layer flux is DEEP PERCOLATION (a loss; count in ledger).
       (Implement the full "drainability" logic: if the cumulative incoming flux exceeds what the layer can drain, the layer is filled toward saturation and any remainder is pushed back up as reduced upstream drainage. Reproduce with unit tests on a 3-layer column.)
 (b) Runoff via SCS curve number:
       CN adjusted for antecedent moisture: CN_dry = 1.4*10^-14 + 0.507*CN - 0.00374*CN^2 + 0.0000867*CN^3 (rounded) ; CN_wet = 5.6*10^-14 + 2.33*CN - 0.0209*CN^2 + 0.000076*CN^3 (rounded)
       Weighted wetness of top zCN depth: weights per compartment wrel_i = wx_i - wx_{i-1}, wx_i = 1.016*(1 - exp(-4.16*(z_i/zCN))) (clipped 0-1); wet_top = sum wrel_i*(theta_i - theta_wp_i)/(theta_fc_i - theta_wp_i) (clipped 0-1)
       CN = round(CN_dry + (CN_wet - CN_dry)*wet_top) ; S = 25400/CN - 254 [mm] ; Ia = 0.05*S
       Runoff Q = (P - Ia)^2 / (P + 0.95*S) if P > Ia else 0 ; Infiltration = P - Q
       Management: CN adjusted by (1 + pct/100); if bunds with height > 1 mm or runoff inhibition -> Q = 0 (water ponds as surface storage up to bund height).
 (c) Soil evaporation (two-stage, Ritchie-type via REW):
       Kex = max soil evaporation coefficient (default 1.1); fwcc canopy-shade adjustment (default 50 %).
       EsPot = Kex*(1 - CCadj)*ET0 ; capped by EsPotMax = Kex*ET0*(1 - CCxW*fwcc/100) ; during senescence (t > Senescence and CCxAct>0) EsPot *= (1 - CCxAct*fwcc/100*mult) with
           mult = 1 if CC <= CCxAct/2 ; 0 if CC > CCxAct ; else (CCxAct - CC)/(CCxAct/2); lower bound EsPotMin = Kex*(1 - CCxActAdj)*ET0 with CCxActAdj = 1.72*CCxAct - CCxAct^2 + 0.3*CCxAct^3
       Mulch: EsPot *= (1 - fMulch*mulchPct/100) when no surface ponding. Irrigation wetting fraction: if irrigated and no rain>1 mm and no ponding: EsPot *= WetSurf/100 ; take the min of mulch/wetting adjusted values.
       Stage 1 (energy-limited): evaporation from surface wetness Wsurf up to REW after wetting (Wsurf = min(Infl, REW)); extract from top EvapZmin layer water above air-dry.
       Stage 2 (falling rate): Kr = (exp(fevap*Wrel) - 1)/(exp(fevap) - 1) with Wrel = (W_act - W_dry)/(W_upper - W_dry) , W_upper = Wstage2*(W_sat - (W_fc - REW)) + (W_fc - REW);
           evaporation layer deepens from EvapZmin to EvapZmax (step 1 mm) when Wrel < fWrelExp*(EvapZmax - EvapZ)/(EvapZmax - EvapZmin); EsAct = Kr*EsPot limited by available water. Sub-daily iteration with EvapTimeSteps (default 20).
       Defaults [VERIFIED in source]: REW = 9.0 mm if not texture-adjusted, EvapZmin = 0.15 m, EvapZmax = 0.30 m, Kex = 1.1, fevap = 4, fWrelExp = 0.4, fwcc = 50 %, zCN = 0.3 m, zGerm = 0.3 m, fshape_cr = 16.
       Texture-based REW (literature, FAO-56 Table 19 - Codex must re-check against the table and ship as an editable CSV with provenance 'literature_FAO56'): sand 2-7, loamy sand 4-8, sandy loam 6-10, loam 8-10, silt loam 8-11, silty clay loam 8-11, silty clay 8-12, clay 8-12 (mm; use midpoint, carry +/- half-range as uncertainty).
 (d) Capillary rise from water table: Ksat-based steady upward flux using aCR, bCR per texture, limited by gradient; Level 1: IMPLEMENT but default OFF unless water_table_depth is provided (most Rajasthan farmland: deep water table -> negligible).
 (e) Root-zone water: TAW = 1000*sum_i (theta_fc_i - theta_wp_i)*dz_i*rootfrac_i ; Dr = 1000*sum_i (theta_fc_i - theta)*dz_i*rootfrac_i ; use the stricter of root-zone vs. topsoil (zTop) depletion fraction when computing stress (as in the crop code).
 (f) Irrigation application:  gross = net/eff_app ; net requirement = Dr (refill to FC) for SOIL_MOISTURE_THRESHOLD policy when Dr/TAW > (1 - SMT/100) ; max depth cap ; interval ; season cap ; schedule list; special mode NET (irrigate to keep the SMT) ; rainfall forecast skip rule (optional extension: skip if forecast rain >= 0.5*Dr in next 48 h with probability >= 0.7).

 Level 2 extension (SoilWaterModel.supports adds "richards"): 1-D Richards equation with Mualem-van Genuchten via an implicit finite-volume scheme (use scipy.integrate / or fipy-like own tridiagonal + Picard iteration) ONLY for plots where a measured retention/Ksat curve and sensors exist. Level 1 stays default.
 Tile/lateral drainage (optional, off by default): remove water from layers between drain depth and target level at rate coefficient.

 MASS BALANCE (hard test): sum(P + Irr + CR + GWin) - sum(Runoff + Es + Tr + DeepPerc + TileDrain) = dStorage(soil + surface) within 0.5 mm per season (assert; raise MassBalanceError).
 API: class LayeredWaterBalance: step(state, forcing: DailyForcing, actions) -> (new_state, fluxes) ; pure functions per process listed above (drainage(), curve_number_runoff(), soil_evaporation(), infiltration(), root_zone_water()) so each is unit-testable alone.
TESTS: (1) bucket test: no crop, no rain, no ET -> state unchanged; (2) saturated column drains to FC in a time consistent with tau (analytic for one layer: theta(t) relation via the exponential drainage law integrated numerically); (3) curve number: P=50 mm, CN=75 -> S=84.67 mm, Ia=4.23, Q=(50-4.23)^2/(50+0.95*84.67)=16.1 mm (hand-check to 0.05 mm); (4) mass balance 10-year random-forcing run closes.
"""
