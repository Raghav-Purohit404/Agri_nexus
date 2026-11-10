"""
FILE: farm_twin/models/soil/rothc.py
PURPOSE: Soil organic carbon dynamics (monthly) - five-pool RothC-type model; answers 'how will soil carbon change under crop/residue/manure/PV-shade scenarios'.

POOLS (t C/ha in the modelled topsoil layer, default 23 cm): DPM (decomposable plant material), RPM (resistant plant material), BIO (microbial biomass), HUM (humified OM), IOM (inert, k=0).
RATE CONSTANTS [VERIFIED in the reference port] (per year): k_DPM = 10.0, k_RPM = 0.3, k_BIO = 0.66, k_HUM = 0.02, k_IOM = 0.
RATE MODIFYING FACTORS (monthly):
   a (temperature) = 47.91 / (1 + exp(106.06/(T_air_monthly_C + 18.27)))    [VERIFIED]  (a = 0 if T < -5.0)
   b (moisture) from topsoil moisture deficit: accumulated TSMD:
        maxTSMD = -(20 + 1.3*clay_pct - 0.01*clay_pct^2) * (depth_cm/23)         [VERIFIED; for bare soil the reference port divides by 1.8]
        b = 1.0 if acc_TSMD > 0.444*maxTSMD  (i.e. wet side)  else  b = 0.2 + (1 - 0.2)*(maxTSMD - acc_TSMD)/(maxTSMD - 0.444*maxTSMD) ; floor 0.2.   [Codex: confirm sign convention with a worked example in tests - TSMD is negative-valued deficit]
        TSMD update each month: (rain - open-water-evaporation*0.75 [pot. ET = pan/open-water evap x 0.75]) : if cropped: TSMD_new = min(0, TSMD_old + rain - 0.75*evap) bounded below by maxTSMD; if bare: evaporation rate x ... (the original uses unlimited bare-soil evaporation); our implementation lets the FarmState engine pass ACTUAL ET and root-zone deficit from the daily water model aggregated monthly as the preferred moisture driver ('b_from_daily_water_model=True'); fall back to the TSMD form otherwise.
   c (soil cover) = 0.6 if plant-covered (growing season / green cover) else 1.0   - NOTE: the reference Python port inspected for this blueprint does NOT apply this factor in its decay step (only the bare-soil TSMD limit); the original RothC documentation applies it. Codex: IMPLEMENT c = 0.6/1.0 as a configurable switch, DEFAULT ON, and unit-test both modes; record the decision in docs/model_decisions.md.
   Effective rate: k_eff = k * a * b * c ; pool decay over a month: C(t+1/12) = C(t)*exp(-k_eff/12).
PARTITIONING of decomposed carbon (clay-dependent):
   x = 1.67*(1.85 + 1.60*exp(-0.0786*clay_pct))              [VERIFIED]
   CO2 fraction = x/(x+1) ; BIO fraction = 0.46/(x+1) ; HUM fraction = 0.54/(x+1)       [VERIFIED]
   each of DPM, RPM, BIO, HUM decomposes into CO2, BIO, HUM with these fractions (BIO and HUM products re-enter their own pools).
INPUTS (monthly): plant residue + root carbon input C_in (t C/ha) split into DPM and RPM by the DPM/RPM ratio (default 1.44 for crops and improved grassland, 0.25 for woodland/scrub: literature, flagged), farmyard manure input FYM (t C/ha) split DPM:RPM:HUM = 0.49:0.49:0.02 (literature, flagged).
   C input from the crop model: root + stubble + (1 - removal_fraction)*aboveground residue: C_in = 0.45*(residue dry matter t/ha) ; allow override with measured C fraction.  ROOT BIOMASS ESTIMATE: root:shoot ratio by crop (table with placeholders) because the crop engine does not simulate roots mass.
   Irrigation/rain only affect via b. Tillage multiplier optional (default 1).
INITIALISATION from measured SOC:
   TOC (t C/ha) = OC_pct/100 * bulk_density(t/m3) * depth_m * 10000  [= OC% * BD * depth_cm]
   IOM = 0.049 * TOC^1.139  (Falloon et al. 1998 equation - literature, UNVERIFIED in this blueprint; Codex: confirm)
   Then either (a) equilibrium-run spin-up: choose C_in such that model reaches TOC under long-term mean climate (solve by bisection on C_in), keeping IOM fixed; or (b) when pools unknown start with typical proportions and spin-up with historical management 30 years; (a) is DEFAULT because only TOC is typically measured. Output uncertainty: pool split is ESTIMATED (+/- wide) even though TOC is MEASURED.
OUTPUT: monthly pools, CO2-C respired, delta SOC, SOC at 1/5/10 yrs with uncertainty (Monte Carlo over C_in, k multipliers lognormal CV 20 %, clay +/-3 %).
CARBON ACCOUNTING for decision-making: report change in SOC stock t C/ha and tCO2e = 3.667*tC ; DO NOT claim carbon-credit eligibility; verification protocols are out of scope.
VALIDATION: (1) mass balance: C_in - CO2_out = dC_total within 1e-9; (2) analytic one-pool test: with only DPM and a=b=c=1, C(t)=C0*exp(-10 t); (3) equilibrium test: constant inputs for 1000 years converge (tolerance 0.1 %); (4) regression: reproduce a published RothC test case if supplied by user.
SHADE EFFECT (agrivoltaic): soil temperature under panels is lower -> a computed with `T_air + dT_soil_shade` and b computed from the reduced-ET water balance; both come from the microclimate factors.
TESTS: as above.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


POOL_K_YR = {"DPM": 10.0, "RPM": 0.3, "BIO": 0.66, "HUM": 0.02, "IOM": 0.0}


def decay_pool(
    carbon_tC_ha: float,
    k_per_year: float,
    dt_years: float,
    temperature_modifier: float = 1,
    moisture_modifier: float = 1,
    cover_modifier: float = 1,
) -> tuple[float, float]:
    """Exact first-order pool decay over dt_years; returns remaining pool and respired/decomposed carbon."""
    if min(carbon_tC_ha, k_per_year, dt_years, temperature_modifier, moisture_modifier, cover_modifier) < 0:
        raise ValueError("pool, rate, duration and modifiers must be non-negative")
    remaining = carbon_tC_ha * math.exp(
        -k_per_year * temperature_modifier * moisture_modifier * cover_modifier * dt_years
    )
    return remaining, carbon_tC_ha - remaining


@dataclass(frozen=True)
class RothCFlux:
    pools_tC_ha: dict[str, float]
    co2_c_tC_ha: float
    carbon_input_tC_ha: float
    residual_tC_ha: float
    fidelity: str = "L1_SPEC_UNVALIDATED"


def modifiers(
    temperature_c: float,
    clay_pct: float,
    tsmd_mm: float,
    depth_cm: float = 23,
    covered: bool = False,
    cover_factor_enabled: bool = True,
) -> tuple[float, float, float]:
    if temperature_c < -5:
        a = 0.0
    else:
        a = 47.91 / (1 + math.exp(min(700, 106.06 / (temperature_c + 18.27))))
    max_tsmd = -(20 + 1.3 * clay_pct - 0.01 * clay_pct**2) * (depth_cm / 23)
    if tsmd_mm > 0.444 * max_tsmd:
        b = 1.0
    else:
        b = max(0.2, 0.2 + 0.8 * (max_tsmd - tsmd_mm) / (max_tsmd - 0.444 * max_tsmd))
    c = 0.6 if covered and cover_factor_enabled else 1.0
    return a, b, c


def rothc_month(
    pools_tC_ha: dict[str, float],
    *,
    temperature_c: float,
    clay_pct: float,
    tsmd_mm: float,
    plant_input_tC_ha: float = 0,
    fym_input_tC_ha: float = 0,
    dpm_rpm_ratio: float = 1.44,
    covered: bool = False,
    cover_factor_enabled: bool = True,
    depth_cm: float = 23,
) -> RothCFlux:
    names = tuple(POOL_K_YR)
    pools = {name: float(pools_tC_ha.get(name, 0)) for name in names}
    if any(value < 0 for value in pools.values()) or min(plant_input_tC_ha, fym_input_tC_ha) < 0:
        raise ValueError("carbon pools and inputs must be non-negative")
    a, b, c = modifiers(temperature_c, clay_pct, tsmd_mm, depth_cm, covered, cover_factor_enabled)
    x = 1.67 * (1.85 + 1.60 * math.exp(-0.0786 * clay_pct))
    co2_fraction, bio_fraction, hum_fraction = x / (x + 1), 0.46 / (x + 1), 0.54 / (x + 1)
    decomposed: dict[str, float] = {}
    co2 = 0.0
    for name, k in POOL_K_YR.items():
        remaining, loss = decay_pool(pools[name], k, 1 / 12, a, b, c)
        decomposed[name] = loss
        pools[name] = remaining
        co2 += loss * co2_fraction
    total_decomp = sum(decomposed.values())
    pools["BIO"] += total_decomp * bio_fraction
    pools["HUM"] += total_decomp * hum_fraction
    plant = plant_input_tC_ha
    pools["DPM"] += plant * dpm_rpm_ratio / (1 + dpm_rpm_ratio)
    pools["RPM"] += plant / (1 + dpm_rpm_ratio)
    pools["DPM"] += fym_input_tC_ha * 0.49
    pools["RPM"] += fym_input_tC_ha * 0.49
    pools["HUM"] += fym_input_tC_ha * 0.02
    inputs = plant_input_tC_ha + fym_input_tC_ha
    residual = inputs - co2 - (sum(pools.values()) - sum(float(pools_tC_ha.get(n, 0)) for n in names))
    return RothCFlux(pools, co2, inputs, residual)
