"""
FILE: farm_twin/core/units.py
PURPOSE: Unit registry + conversions at I/O boundaries. Internal code uses canonical units (CONVENTIONS.md).

IMPLEMENT (wrap `pint`; do not write a unit library):
    ureg with: sqft = 0.09290304 m**2. Regional land units (bigha, kanal, gaj) MUST be per-property configurable
    factors, never hard-coded, because their size differs by state/region.
    to_canonical(value, unit) -> (float, canonical_unit)
    convert(value, from_unit, to_unit) -> float
    Soil-lab converters (each with a unit test):
        ppm_to_kg_per_ha(conc_mg_per_kg, bulk_density_g_cm3, depth_m) = conc * bd * depth * 10
            derivation: kg/ha = mg/kg * 1e-6 * (bd*1000 kg/m3) * depth_m * 1e4 m2/ha
        percent_to_fraction; 1 dS/m == 1 mS/cm (identity)
        meq_per_L_from_mg_per_L(ion, mg_per_L) with equivalent weights
            Ca 20.04, Mg 12.15, Na 22.99, K 39.10, Cl 35.45, SO4 48.03, HCO3 61.02, CO3 30.0
        OC_percent_to_OM_percent(oc) = oc * 1.724   (Van Bemmelen factor; keep configurable)
        mm_over_area_to_m3(mm, area_m2) = mm * area_m2 / 1000
    RANGES table + validate_range(name, value, unit) -> RangeError:
        pH 3.5-10.5; EC 0-60 dS/m; OC 0-12 %; sand/silt/clay each 0-100, sum within 100 +/- 2;
        bulk density 0.8-1.9 g/cm3; theta 0-0.7; air temperature -40..60 C; rainfall 0-1000 mm/day;
        ET0 0-15 mm/day; Rs 0-40 MJ/m2/day.
TESTS: sqft->m2 for 800/600/1300 sq ft (74.32 / 55.74 / 120.77 m2); ppm_to_kg_per_ha(10, 1.4, 0.15) == 21.0.
"""
