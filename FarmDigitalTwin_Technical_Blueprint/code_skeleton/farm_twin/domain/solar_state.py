"""
FILE: farm_twin/domain/solar_state.py
PURPOSE: SolarState: description of PV assets and their running state.

IMPLEMENT: class PVConfig: kind {GROUND_FIXED, GROUND_TRACKER_1AXIS, ELEVATED_AGRIVOLTAIC_FIXED, VERTICAL_BIFACIAL, ROOFTOP},
        kWp, module params (pdc0_W, gamma_pdc_per_C, bifaciality, transmittance for semi-transparent), tilt_deg, azimuth_deg (180=south),
        row_pitch_m, clearance_height_m (lowest panel edge), collector_width_m (slant), gcr, n_rows, inverter (pdc0, eta_nom), losses (soiling, mismatch, wiring ...),
        degradation_pct_per_year, albedo, mounting_temp_model {open_rack, close_mount}, capex_inr, opex_inr_per_year
    class SolarState: configs by plot, hourly_generation series (MODEL_PREDICTED), soiling_state (cumulative dust loss; Rajasthan: significant), degradation_age_years.
TESTS: GCR == collector_width_slant / pitch for fixed-tilt rows (GCR uses the SLANT width; the horizontal footprint ratio is collector_width_slant*cos(tilt)/pitch and must be exposed separately as `footprint_ratio`).
"""
