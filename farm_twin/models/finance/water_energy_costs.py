"""
FILE: farm_twin/models/finance/water_energy_costs.py
PURPOSE: Cost of pumping/irrigation water and energy used by crop budgets.

IMPLEMENT: pumping energy kWh/m3 = (rho*g*H_total)/(3.6e6*eta_pump*eta_motor) with H_total = static lift + drawdown + friction/pressure head (m) ; = 0.00272*H/eta_total  [kWh/m3 with H in m, derivation: 9.81*1000*H/3.6e6 = 0.002725*H]; groundwater depletion cost option (shadow price INR/m3, user-set, default 0); tanker/purchased water cost; drip/sprinkler energy from operating pressure.
  Irrigation requirement planner: monthly net requirement (mm) -> gross using system efficiency -> m3 for the area -> compare with water availability series (domain/water_state.py) -> shortfall m3 and the yield penalty via crop engine runs (NOT a linear shortcut).
TESTS: 30 m head, eta 0.5 -> 0.1635 kWh/m3.
"""

from __future__ import annotations

from dataclasses import dataclass

from farm_twin.core.errors import MissingDataError


G = 9.81
WATER_DENSITY_KG_M3 = 1000.0
J_PER_KWH = 3.6e6


def pumping_energy_kwh_m3(total_head_m: float, pump_efficiency: float, motor_efficiency: float = 1.0) -> float:
    if total_head_m < 0 or not 0 < pump_efficiency <= 1 or not 0 < motor_efficiency <= 1:
        raise ValueError("head must be non-negative and efficiencies in (0,1]")
    return WATER_DENSITY_KG_M3 * G * total_head_m / (J_PER_KWH * pump_efficiency * motor_efficiency)


@dataclass(frozen=True)
class IrrigationCost:
    gross_depth_mm: float
    volume_m3: float
    energy_kwh: float
    water_cost_inr: float
    energy_cost_inr: float
    shortfall_m3: float


def irrigation_cost(
    net_depth_mm: float,
    area_m2: float,
    application_efficiency: float,
    energy_kwh_m3: float,
    tariff_inr_kwh: float | None,
    water_cost_inr_m3: float | None,
    available_m3: float | None = None,
) -> IrrigationCost:
    required = []
    if tariff_inr_kwh is None:
        required.append("tariff_inr_kwh")
    if water_cost_inr_m3 is None:
        required.append("water_cost_inr_m3")
    if required:
        raise MissingDataError("Economic inputs required", context={"missing": required})
    if application_efficiency <= 0 or application_efficiency > 1 or net_depth_mm < 0 or area_m2 < 0:
        raise ValueError("invalid irrigation depth, area, or efficiency")
    gross = net_depth_mm / application_efficiency
    volume = gross * area_m2 / 1000
    delivered = min(volume, available_m3) if available_m3 is not None else volume
    shortfall = max(0, volume - delivered)
    energy = delivered * energy_kwh_m3
    return IrrigationCost(
        gross, delivered, energy, delivered * float(water_cost_inr_m3), energy * float(tariff_inr_kwh), shortfall
    )
