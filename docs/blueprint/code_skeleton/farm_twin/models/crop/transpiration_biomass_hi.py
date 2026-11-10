"""
FILE: farm_twin/models/crop/transpiration_biomass_hi.py
PURPOSE: Transpiration demand/actual, biomass accumulation, harvest index and yield.

1. TRANSPIRATION
   Potential transpiration TrPot = Kcb * CC* * ET0, where CC* = 1.72*CC - CC^2 + 0.3*CC^3 capped at 1 (adjusts cover to transpiring area). Optional crop-ageing decline of Kcb after senescence onset by `fage` %/day (default off; enable only if golden tests demand it).
   (Aging: Kcb declines late season by `fage` (crop file; default 0.3 %/day) after senescence onset: Kcb_eff = Kcb - (t - t_age_start)*(fage/100)*CC^? ... keep optional, default off, validate on golden.)
   TrAct = TrPot * Ks_sto (and * Ks_aer if aeration stress; * (1 - salinity if config pathway 'transpiration')). Extraction: distribute TrAct over root layers with a root-sink profile (S_i proportional to exp-shaped root density, e.g. SxTop=0.048,SxBot=0.012 m3/m3/day maxima, linearly interpolated with depth; per-layer actual limited by water above theta_wp + stress). Keep the 'max extraction per layer' logic and the redistribution of unmet demand to wetter layers (upwards/downwards) - needed for mass balance + realistic stress onset.
2. BIOMASS (daily)  [VERIFIED structure]
   dB = WP_adj * (Tr / ET0) * Ks_temp_bio * f_co2 * Ks_sal * Ks_N * Ks_PK       [t/ha/day when WP in t/ha and Tr/ET0 in mm/mm; WP stored normalised in g/m2 -> 10 g/m2 = 0.1 t/ha: convert once at boundary]
   WP_adj (water productivity adjusted for crop type and growth stage): CropType 1 (leafy) and 2 (root/tuber) and 3 (fruit/grain): during yield formation after HIstart for type 3, WP is reduced by WPy % (crop param, e.g. 100 -> no reduction) : WP_adj = WP * (1 - (1 - WPy/100) * fswitch) with fswitch = fraction of yield-formation period elapsed (0..1) ; ET0-normalised WP* ; WP is in g biomass per m2 per mm Tr/ET0-normalised, CO2-adjusted as WP(CO2) = WP * (CO2_ref... ) -> Level 1: f_co2 = 1.0 (configurable table `co2_ppm -> fCO2`), 
   Biomass is capped: B_total_cum accumulates only while crop alive; with cold stress on dB: dB *= Ks_temp where temperature stress on biomass uses GDD_lo/GDD_up thresholds.
   Carry `B_nostress` in parallel (dB with all Ks = 1 and CC no-stress) for the stress report and for HI pre-flowering factor.
   SHADE / LIGHT LIMITATION (NEW - agrivoltaics; see models/agrivoltaic/crop_coupling.py): dB = min(dB_water, RUE * fPAR * PAR_ground_MJ) when `light_limited=True`; RUE crop parameter in g DM per MJ intercepted PAR (calibratable; placeholder priors per crop, flagged); fPAR = CC_effective (cover proxy), Level 1.
3. HARVEST INDEX
   Reference HI build-up, logistic [VERIFIED form] from start of yield formation (t = days since HIstart, adjusted):
        HIref(t) = HIini*HI0 / (HIini + (HI0 - HIini)*exp(-HIGC*t)),  HIini = 0.01
        HIGC found by search: smallest HIGC (step 0.001) such that HIref(YldFormCD) > 0.98*HI0 (if HIest >= HI0 subtract one step)
        Linear tail: tLinSwitch/dHILinear computed by scanning ti = 1..YldFormCD for the first ti where HIest = HI(ti) + (YldFormCD-ti)*(HI(ti)-HI(ti-1)) > HI0; switch at ti-1; dHILinear = (HI0 - HI(tSwitch))/(YldFormCD - tSwitch). After tLinSwitch HI grows linearly (applies to root/tuber; for grain-type crops keep logistic).
        Root/tuber crops (CropType 2) and fruit (3) may have pre-yield HI offset by `dHI0` bound.
   Adjustments (multiplicative on HIref): HI_adj = HIref * f_pre * f_post * f_pol, bounded to [0, HI0*(1 + dHI0/100)]. Components:
        f_pre : effect of water stress before flowering. Compute from biomass ratio B/B_nostress at start of flowering and from the stress counters of canopy expansion & stomata: 
                reduction when canopy growth stress is moderate can INCREASE HI for some crops (a_HI positive: 'HI increase from pre-flowering stress', crop param `a_HI`) but stomatal closure stress before flowering decreases it by `b_HI`. Use crop params a_HI, b_HI, dHI_pre.
        f_post: effect of stress during yield formation: canopy-senescence stress, stomatal-closure stress (b_HI-like params) bounded by dHI0 and a 'HIini freeze' when canopy collapses.
        f_pol : pollination: fraction of flowers pollinated = clip(1 - heat/cold/water pollination failure, 0,1) (accumulated over flowering days, weighted by flowering duration); f_pol multiplies HI and persists.
   Yield(t) = B(t) * HI_adj(t) * (1/100 factor for unit) ; Final dry yield at maturity; fresh yield = dry / (1 - FC) with FC water-content fraction of the harvested product (crop file: e.g. grain 0.12 -> fresh = dry/(1-0.12)); report BOTH, always labelled.
   NOTE: the hard-to-copy details above (a_HI, b_HI exact stress formulas) must be implemented so that the GOLDEN fixtures (Tunis wheat, 6 seasons rainfed & irrigated) reproduce yields within +/-3 % and seasonal irrigation within +/-5 mm; failing golden tests block promotion of this module.
TESTS: HIGC search gives value for wheat (HI0=0.48, YldFormCD per library); HIref(YldFormCD)=0.98*HI0 +/- 0.01; dB scales linearly with Tr/ET0; mass accounting B(t) cumulative.
"""
