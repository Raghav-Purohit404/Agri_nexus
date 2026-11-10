"""
FILE: farm_twin/domain/infrastructure_state.py
PURPOSE: Capital assets other than PV: borewell/pump, drip network, tanks, fences, sheds, soil-moisture sensors, weather station.

IMPLEMENT: class InfraAsset(id, kind, plot_id|None, capex_inr, install_date, life_years, salvage_frac, opex_inr_per_year, capacity {unit,value},
           status {EXISTING, PLANNED, PROPOSED}), class InfraState(assets, maintenance_log).
           Irrigation-specific: IrrigationSystem(method {SURFACE, DRIP, SPRINKLER, MANUAL}, application_efficiency 0-1, wetted_surface_fraction 0-1,
           pump kW, flow_m3_h, energy_kwh_per_m3).  application_efficiency feeds directly into the crop-water solver (irrigation applied = net/eff).
"""
