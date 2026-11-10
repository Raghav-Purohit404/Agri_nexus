"""
FILE: farm_twin/models/finance/cashflow.py
PURPOSE: Financial engine: per-plot and property cashflows, NPV/IRR/payback/LCOE, risk metrics. Annual step (monthly optional for working-capital checks).

IMPLEMENT:
 1. Crop budget per plot-season: revenue = yield_t_ha * area_ha * price_inr_per_t (PRICE = scenario draw; use fresh vs dry basis consistently; price at farm gate = mandi modal - transport - commission (user params)); costs = seed + fertiliser + amendment + pesticide + labour (days*wage) + irrigation (water cost + pumping kWh*tariff) + machinery + insurance + interest on working capital + land lease if any. Everything per season with timing (month index) for monthly cashflow.
 2. PV project cashflow: year-0 capex; yearly revenue = self-consumed kWh*avoided tariff + exported kWh*export tariff (per TariffSchedule rules; net-metering banking logic: monthly net import/export, credit carry-forward with expiry) ; opex (cleaning, O&M % of capex, insurance), inverter replacement at year ~10-12 (cost % of capex), degradation (0.5 %/yr default), tax/depreciation optional (user switches), subsidies as explicit user-entered line items (never assumed).
 3. Agrivoltaic combined: crop revenue under panels (from coupling) + PV revenue; shared structure cost; extra labour/ machinery constraints (user parameter: reduced mechanisation).
 4. Metrics: NPV = sum_t CF_t/(1+r)^t ; IRR by Brent root-finder on [-0.99, 10] (return NaN with reason if no sign change); simple and discounted payback (linear interpolation within year); LCOE = (capex + sum PV(opex))/(sum PV(energy)) in INR/kWh with energy discounted at the same rate; benefit-cost ratio; equivalent annual annuity for comparing unequal horizons; minimum cash balance (monthly) and peak funding need.
 5. Real vs nominal: all inputs nominal INR with explicit inflation per series (default 5 % general, electricity tariff escalation 0-3 % user-set, crop price inflation = CPI); discount rate nominal; terminal/salvage value of assets.
 6. RISK: given N joint scenarios (weather x price x tariff) produce distribution of NPV; VaR_alpha, CVaR_alpha (expected NPV of worst (1-alpha) tail; use 0.80/0.90), probability(NPV<0), worst-year cash shortfall probability, downside deviation.
 7. SENSITIVITY: tornado (one-at-a-time +/-20 % on price, yield, capex, tariff, discount rate), Sobol (see uncertainty/sensitivity.py).
 8. Working-capital and credit: simple loan amortisation (EMI = P*r(1+r)^n/((1+r)^n-1) with monthly r), overdraft constraint; the optimiser consumes `budget_by_year`.
 OUTPUT: CashflowResult(series by year/month, kpis, assumptions list with provenance).
RULES: no hard-coded prices, tariffs or subsidies; missing economic inputs raise MissingDataError listing exactly what is needed; every report prints currency, price basis, horizon, discount rate.
TESTS: NPV/IRR vs textbook example (CF = -1000, 300x5, r=10 % -> NPV = 137.24; IRR = 15.24 %); EMI example; payback interpolation; CVaR of known discrete distribution.
"""
