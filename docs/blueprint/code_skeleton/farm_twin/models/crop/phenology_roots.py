"""
FILE: farm_twin/models/crop/phenology_roots.py
PURPOSE: Crop calendar (thermal or calendar time), stage detection, root deepening.

IMPLEMENT:
 1. Growing degree days (daily, from Tmax/Tmin, crop Tbase and Tupp):
      method 1: Tmean = (Tmax+Tmin)/2 clipped to [Tbase, Tupp]; GDD = Tmean - Tbase   (default for most crops)
      method 2: Tmax = min(Tmax, Tupp); Tmin = max(Tmin, Tbase) (cap both); GDD = (Tmax+Tmin)/2 - Tbase
      method 3: clip Tmax,Tmin to [Tbase,Tupp] first, then GDD = (Tmax+Tmin)/2 - Tbase
      (all three exist in the reference implementation; make the method a crop-config enum; default 3 unless crop file says otherwise).
 2. Crop calendar: CalendarType 1 = calendar days, 2 = GDD. Stage lengths (days or GDD) for: emergence, max root, start senescence, maturity, start flowering, flowering length, start yield formation (HIstart), yield formation length. `t_adj = DAP - delayed_days` (type 1) or `GDDcum - delayed_gdd` (type 2). Delays accumulate when stress postpones canopy development (see canopy.py).
 3. Planting-date logic: sowing is permitted only after a rain/irrigation-based window if `sowing_rule` is set: plant on first day in [window_start, window_end] where cumulative rain over the previous N days >= R_mm and soil theta in top 0.1 m >= theta_wp + 0.5*(theta_fc - theta_wp); else force planting at window_end (flag late_sowing). This rule is mandatory for rainfed pearl millet / cluster bean systems.
 4. Root depth (potential) [VERIFIED form]: Zini = Zmin*PctZmin/100; t0 = round(Emergence/2); tmax = MaxRooting;
      Zr(t) = Zmax if t >= tmax ; Zini if t <= t0 ; else Zini + (Zmax - Zini) * ((t - t0)/(tmax - t0))**(1/fshape_r)
      Zr >= Zmin. Actual root growth day step: dZr limited by soil: root zone cannot extend into a layer that is dry (theta < theta_wp + fshape-based threshold) or beyond soil depth/restrictive layer; if water-table or impermeable layer at depth zlimit then Zr = min(Zr, zlimit). Root growth rate max (Zmax-Zmin)/MaxRooting-time scaled by (1 - exp(-xx)) of soil dryness - implement as: Zr_act(t) = Zr_act(t-1) + min(Zr_pot(t)-Zr_pot(t-1), Zr_max_step) * Kroot, Kroot = clip((theta_layer - theta_wp)/(theta_fc - theta_wp) / 0.2, 0, 1) of the layer being entered.
 5. Stage helpers: stage_of(day) -> {EMERGENCE, VEGETATIVE, FLOWERING, YIELD_FORMATION, SENESCENCE, MATURE}; `is_in_flowering`, `is_in_yield_formation` booleans used by stress/HI.
 6. Maturity: crop ends when t_adj >= Maturity OR canopy cover declines below 0.02 after senescence start OR killing frost: Tmin < Tlethal (crop parameter) for 1 day -> status DEAD.
TESTS: wheat Zr(t) monotone, equals Zmax at MaxRooting; GDD methods hand-checked on Tmax=34,Tmin=18,Tbase=0,Tupp=26; delays shift stage dates by exactly the delay.
"""
