"""
FILE: farm_twin/domain/water_state.py
PURPOSE: WaterState at plot AND property level (supply side + storage + fluxes).

IMPLEMENT: class WaterSource(kind in {GROUNDWATER_WELL, RAINWATER_TANK, CANAL, TANKER, FARM_POND, MUNICIPAL}, capacity_m3,
        yield_m3_per_day|None, seasonal_availability: monthly array(12) of m3, quality: ec_dSm, sar, cost_inr_per_m3,
        pumping_kwh_per_m3 (from head/efficiency), reliability: Uncertainty)
    class StorageAsset(volume_m3, level_m3, evap_loss_model, seepage_loss_frac_per_day, catchment_area_m2, runoff_coefficient)
    class WaterState: sources, storages, plot_irrigation_demand_mm (per plot/day), water_balance_ledger (daily list of
        precip, irrigation, runoff, drainage, ET, dStorage, residual) used by the mass-balance checker.
    method: rooftop_harvest_m3(roof_area_m2, rain_mm, first_flush_mm=1.0, coeff=0.8)  -> max(0, rain_mm-first_flush_mm)*roof_area*coeff/1000
TESTS: tank mass balance over a synthetic year closes within 0.1%.
"""
