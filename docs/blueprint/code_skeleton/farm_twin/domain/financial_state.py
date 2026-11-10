"""
FILE: farm_twin/domain/financial_state.py
PURPOSE: FinancialState: capital, prices, costs, cashflow ledger.

IMPLEMENT: Budget(available_capital_inr, borrowing_limit, interest_rate, planning_horizon_years=10, discount_rate (default 0.10, user editable, with scenario range 0.07-0.14)),
    PriceSeries(commodity, unit, history, forecast distribution), InputCostCatalog (seed, urea, DAP, MOP, FYM, gypsum, labour/day, diesel, electricity tariff, water),
    CashflowLedger(entries: date, category, amount_inr, plot_id|None, kind {ACTUAL, PLANNED, SIMULATED}), TariffSchedule(kind {NET_METERING, FEED_IN, SELF_CONSUME_ONLY, TOU}, rates, effective dates).
RULE: SIMULATED and ACTUAL entries are separate kinds and never summed unless the report says so.
"""
