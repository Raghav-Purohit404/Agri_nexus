"""
FILE: farm_twin/voi/value_of_information.py
PURPOSE: Answer 'which measurement/experiment would most reduce decision risk per rupee?'.
IMPLEMENT:
  EVPI = E_theta[ max_d U(d, theta) ] - max_d E_theta[ U(d, theta) ]  computed on the scenario/param ensemble (decisions d = allocations from the payoff table; theta = uncertain parameter draws such as soil EC, Ksat, RUE, tau_eff): EVPI is an UPPER BOUND on what any information can be worth.
  EVSI for a specific measurement m with noise model: preposterior analysis by simulation: for j in 1..J: draw theta_j from the current posterior, simulate the measurement y_j = g(theta_j) + noise, update the posterior (importance reweighting of the ensemble: w_i propto N(y_j | g(theta_i), sigma^2)), choose d*(y_j) maximising weighted expected utility, evaluate its TRUE utility under theta_j. EVSI = mean_j U(d*(y_j), theta_j) - max_d E U(d, theta) ; net value = EVSI - cost(m).
  Candidate measurements (catalogue, editable CSV with costs in INR, noise sd, delay): soil lab test (EC, pH, texture, OC, N, P, K), saturated-paste ECe at depth, irrigation-water analysis, soil-moisture probe network, weather station, ceptometer/PAR survey under panels, test strip trial (crop under panel vs open), yield sampling plots, infiltration test.
  Ranking output: table(measurement, EVSI, cost, net value, ROI, time-to-information) + 'recommended first measurement' + data-quality improvements it would unlock.
  Efficient approximation: because the payoff table is already simulated, preposterior reweighting needs no new simulations.
TESTS: EVPI = 0 when one decision dominates in all draws; EVSI <= EVPI; perfect-information measurement (sigma->0) approaches EVPI.
"""
