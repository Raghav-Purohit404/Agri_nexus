"""
FILE: farm_twin/models/finance/water_energy_costs.py
PURPOSE: Cost of pumping/irrigation water and energy used by crop budgets.

IMPLEMENT: pumping energy kWh/m3 = (rho*g*H_total)/(3.6e6*eta_pump*eta_motor) with H_total = static lift + drawdown + friction/pressure head (m) ; = 0.00272*H/eta_total  [kWh/m3 with H in m, derivation: 9.81*1000*H/3.6e6 = 0.002725*H]; groundwater depletion cost option (shadow price INR/m3, user-set, default 0); tanker/purchased water cost; drip/sprinkler energy from operating pressure.
  Irrigation requirement planner: monthly net requirement (mm) -> gross using system efficiency -> m3 for the area -> compare with water availability series (domain/water_state.py) -> shortfall m3 and the yield penalty via crop engine runs (NOT a linear shortcut).
TESTS: 30 m head, eta 0.5 -> 0.1635 kWh/m3.
"""
