"""
FILE: farm_twin/uncertainty/sensitivity.py
PURPOSE: Global sensitivity analysis to show which uncertain inputs actually matter (drives data-collection priorities and value-of-information).
IMPLEMENT: Morris elementary effects (screening, r=20 trajectories) -> mu*, sigma ; Sobol first-order and total indices via Saltelli sampling (N*(2D+2) runs) with Jansen estimators: S_i = (V - 0.5*mean((f(B)-f(A_B^i))^2))/V ; ST_i = 0.5*mean((f(A)-f(A_B^i))^2)/V ; bootstrap CIs; supports vector outputs (yield, NPV, SOC change, ECe). One-at-a-time tornado for decision-makers. Parameter ranges come from priors/posteriors (log-uniform for rates).
Output table `sensitivity_report` ranking inputs (soil EC, irrigation water EC, rainfall, price, discount rate, tau_eff ...). Used by VOI (voi/sensor_value.py) and by the Planning agent's 'what to measure first' answer.
TESTS: Ishigami function: analytic S1 = (0.314, 0.442, 0), ST = (0.558, 0.442, 0.244) recovered within 0.03 with N=2^14.
"""
