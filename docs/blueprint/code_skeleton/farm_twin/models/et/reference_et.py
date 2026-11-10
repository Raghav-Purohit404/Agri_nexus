"""
FILE: farm_twin/models/et/reference_et.py
PURPOSE: Reference evapotranspiration ET0 (mm/day). Crop model needs daily ET0; compute it OURSELVES from weather so provider ET0 is only a cross-check.

IMPLEMENT FAO-56 Penman-Monteith (daily), Level 1 REQUIRED:
  ET0 = [0.408*D*(Rn - G) + gamma*(900/(T+273))*u2*(es - ea)] / [D + gamma*(1 + 0.34*u2)]
    T = (Tmax+Tmin)/2 ; G = 0 for daily step
    es = (e0(Tmax)+e0(Tmin))/2 ; e0(T) = 0.6108*exp(17.27*T/(T+237.3)) [kPa]
    ea = from Tdew: e0(Tdew); else from RHmean: ea = RHmean/100*(e0(Tmax)+e0(Tmin))/2 ; else (no humidity) ea = e0(Tmin - K0) with K0 = 2 C (arid: use 4 C, FAO-56 allows) -> flag ESTIMATED_LOW_CONF
    D = 4098*e0(T)/(T+237.3)^2  [kPa/C]
    P = 101.3*((293 - 0.0065*z)/293)^5.26 ; gamma = 0.000665*P  [kPa/C]
    Ra (extraterrestrial): dr = 1 + 0.033*cos(2*pi*J/365); delta = 0.409*sin(2*pi*J/365 - 1.39); ws = arccos(-tan(phi)*tan(delta));
         Ra = (24*60/pi)*0.0820*dr*[ws*sin(phi)*sin(delta) + cos(phi)*cos(delta)*sin(ws)]  [MJ/m2/day]
    Rs: measured/provider; if missing -> Hargreaves-Samani Rs = kRs*sqrt(Tmax-Tmin)*Ra with kRs 0.16 interior / 0.19 coastal (ESTIMATED)
    Rso = (0.75 + 2e-5*z)*Ra ; Rns = (1-0.23)*Rs ; Rnl = sigma*((Tmax_K^4 + Tmin_K^4)/2)*(0.34 - 0.14*sqrt(ea))*(1.35*Rs/Rso - 0.35), sigma = 4.903e-9 MJ/K^4/m2/day (Rs/Rso clipped to [0.3,1.0])
    Rn = Rns - Rnl
    u2 from u10 per core wind conversion (providers/base.py)
  Fallback Level 1b (only if no wind/humidity): Hargreaves ET0 = 0.0023*(Tmean+17.8)*sqrt(Tmax-Tmin)*Ra/lambda... implement in mm/day as 0.0023*0.408*Ra*(Tmean+17.8)*sqrt(Tmax-Tmin); flag ESTIMATED with +/-15% uncertainty.
  API: et0_fao56(df, lat_deg, elev_m) -> Series with Quantified provenance; vectorised numpy; unit tests against FAO-56 worked example numbers (Example 18, Bangkok monthly and Example 19 daily Uccle: ET0 = 3.9 mm/day) - Codex: reproduce the published example inputs from the FAO-56 text/tables and assert to 0.05 mm/day.
  ALSO: et0_with_microclimate(df, rs_scale, u2_scale, dT) for the agrivoltaic coupling: recompute with Rs*rs_scale, u2*u2_scale, Tmax/Tmin + dT. (Radiation term is reduced under panels; wind term scaled; both effects are separately switchable for sensitivity analysis.)
TESTS: Uccle daily example; monotonicity (ET0 increases with Rs, u2, T); ET0 >= 0.
"""
