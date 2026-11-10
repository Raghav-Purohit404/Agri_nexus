"""
FILE: farm_twin/agents/tools/registry.py
PURPOSE: Typed tool layer between LLM agents and the deterministic scientific core. Agents NEVER compute science themselves; they call tools.

IMPLEMENT: @tool-style registry where each tool = (name, pydantic input schema, pydantic output schema, handler, side_effect {NONE, READ_EXTERNAL, WRITE_STATE, WRITE_RECOMMENDATION, EXTERNAL_ACTION}, requires_approval: bool, timeout_s, idempotent: bool, allowed_agents: set[str]).
 Wrapper behaviour for every call: (1) validate args with pydantic (reject unknown fields); (2) check allowed_agents; (3) approval gate for side_effect >= WRITE_STATE where requires_approval (raises ApprovalRequiredError -> graph interrupt); (4) execute with timeout & retry on transient errors only; (5) catch FarmTwinError -> return {ok:false, error:{code,message,context}} (never raise into the LLM loop); (6) write tool_call row (args, result hash, duration); (7) create EvidenceItem from output; (8) truncate large outputs to a summary + artifact reference (arrays are never pasted into prompts).
 TOOL CATALOGUE (name: purpose [side effect]):
   property.create/update_plot, plot.import_geometry [WRITE_STATE, approval=no (user supplied)]
   data.upload_soil_report, data.parse_soil_report, data.confirm_fields [WRITE_STATE]
   data.fetch_weather(lon,lat,range), data.fetch_forecast, data.fetch_soil_prior, data.fetch_prices, data.fetch_satellite_stats [READ_EXTERNAL]
   quality.run_checks(plot|property), quality.completeness(plot, model) [NONE]
   soil.estimate_properties(plot) (pedotransfer, returns ESTIMATED with uncertainty), soil.salinity_assess(plot), soil.amendment_plan(plot), soil.carbon_projection(plot, scenario)
   crop.simulate_season(plot, crop, planting_date, irrigation_policy, n_weather), crop.compare_crops(plot, crop_list), crop.irrigation_schedule(plot, horizon_days)
   water.balance(property, scenario), water.storage_sizing
   solar.estimate_energy(plot, pvconfig), solar.size_layout(plot, constraints)
   agrivoltaic.evaluate(plot, pv_config, crop) (returns RY, LER, flags unvalidated)
   finance.cashflow(scenario), finance.compare(scenario_ids)
   uncertainty.run_ensemble(scenario, n), uncertainty.sensitivity(scenario)
   optimize.allocate(property, objectives, constraints, risk_lambda), optimize.pareto(...)
   voi.rank_measurements(property)
   calibration.run(plot|farm, model), calibration.status, calibration.history [promotion done ONLY by the gate; tool cannot override it]
   loop.record_recommendation [WRITE_RECOMMENDATION], loop.record_outcome [WRITE_STATE], loop.error_report
   report.build(scenario_ids, audience) -> artifact [NONE]
   approval.request(recommendation_id) [creates ApprovalRequest; human decides]
 TESTS: schema rejection, allowed_agents enforcement, approval gating, error-to-dict conversion, large-output truncation.
"""
