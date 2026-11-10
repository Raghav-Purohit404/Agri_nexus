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

from __future__ import annotations


import pint

from farm_twin.core.errors import RangeError, UnitError

ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
ureg.define("sqft = 0.09290304 * meter ** 2")
ureg.define("INR = [currency]")

CANONICAL = {
    "area": "m^2",
    "length": "m",
    "water_depth": "mm",
    "flux": "mm/day",
    "theta": "dimensionless",
    "temperature": "degC",
    "radiation": "MJ/m^2/day",
    "yield": "tonne/hectare",
    "carbon": "tonne/hectare",
    "money": "INR",
    "energy": "kWh",
    "ec": "dS/m",
    "pressure": "kPa",
}
RANGES: dict[str, tuple[float, float, str]] = {
    "pH": (3.5, 10.5, "dimensionless"),
    "EC": (0, 60, "dS/m"),
    "OC": (0, 12, "%"),
    "sand": (0, 100, "%"),
    "silt": (0, 100, "%"),
    "clay": (0, 100, "%"),
    "bulk_density": (0.8, 1.9, "g/cm^3"),
    "theta": (0, 0.7, "dimensionless"),
    "air_temperature": (-40, 60, "degC"),
    "rainfall": (0, 1000, "mm"),
    "ET0": (0, 15, "mm/day"),
    "Rs": (0, 40, "MJ/m^2/day"),
}


def convert(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return float(value)
    try:
        return float((value * ureg(from_unit)).to(to_unit).magnitude)
    except (pint.errors.PintError, TypeError, ValueError) as exc:
        raise UnitError(f"Cannot convert {from_unit!r} to {to_unit!r}") from exc


def to_canonical(value: float, unit: str) -> tuple[float, str]:
    aliases = {
        "sqft": ("area", "m^2"),
        "ft^2": ("area", "m^2"),
        "dS/m": ("ec", "dS/m"),
        "mS/cm": ("ec", "dS/m"),
        "mm": ("water_depth", "mm"),
        "m": ("length", "m"),
        "kg/ha": ("mass_area", "kg/ha"),
        "t/ha": ("yield", "tonne/hectare"),
        "MJ/m2/day": ("radiation", "MJ/m^2/day"),
        "m3/m3": ("theta", "dimensionless"),
        "%": ("fraction", "dimensionless"),
        "INR": ("money", "INR"),
        "kWh": ("energy", "kWh"),
    }
    if unit in aliases:
        _, target = aliases[unit]
        if unit == "%":
            return value / 100.0, target
        return convert(value, unit, target), target
    for target in CANONICAL.values():
        try:
            return convert(value, unit, target), target
        except UnitError:
            continue
    raise UnitError(f"No canonical unit registered for {unit!r}")


def validate_range(name: str, value: float, unit: str | None = None) -> float:
    if name not in RANGES:
        raise UnitError(f"No range registered for {name!r}")
    low, high, expected_unit = RANGES[name]
    converted = convert(value, unit, expected_unit) if unit and unit != expected_unit else value
    if not low <= converted <= high:
        raise RangeError(
            f"{name}={converted:g} outside [{low:g}, {high:g}] {expected_unit}",
            context={"variable": name, "value": converted, "unit": expected_unit},
        )
    return converted


def ppm_to_kg_per_ha(conc_mg_per_kg: float, bulk_density_g_cm3: float, depth_m: float) -> float:
    return conc_mg_per_kg * bulk_density_g_cm3 * depth_m * 10.0


def percent_to_fraction(value_pct: float) -> float:
    return value_pct / 100.0


def meq_per_L_from_mg_per_L(ion: str, mg_per_L: float) -> float:
    equivalent_weight = {
        "Ca": 20.04,
        "Mg": 12.15,
        "Na": 22.99,
        "K": 39.10,
        "Cl": 35.45,
        "SO4": 48.03,
        "HCO3": 61.02,
        "CO3": 30.0,
    }
    try:
        return mg_per_L / equivalent_weight[ion]
    except KeyError as exc:
        raise UnitError(f"Unknown ion {ion!r}") from exc


def oc_percent_to_om_percent(oc: float, factor: float = 1.724) -> float:
    return oc * factor


def mm_over_area_to_m3(depth_mm: float, area_m2: float) -> float:
    return depth_mm * area_m2 / 1000.0
