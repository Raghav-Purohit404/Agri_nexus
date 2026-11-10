"""
FILE: farm_twin/loop/feedback.py
PURPOSE: Close the loop: recommendation -> approval -> execution -> outcome -> error analysis -> calibration -> better recommendation.
IMPLEMENT:
  record_recommendation(scenario_result, chosen_plan) writes recommendation with EXPECTED KPI distributions and assumptions (immutable).
  record_approval(...) (human decision) ; record_execution(intervention actual_payload) ; record_outcome(plot, variable, observed value/time) auto-links to the prediction made for that (plot, variable, date, run) and computes error, standardised error z = (obs - mean)/sd, PIT value, and whether obs fell in the 90 % interval.
  error_analysis(): attribute error by driver: re-run the SAME plan with ACTUAL weather & ACTUAL interventions (hindcast) -> splits total error into (i) weather realisation, (ii) management deviation, (iii) residual model/parameter error. Only (iii) feeds calibration.
  triggers: after each harvest or batch of >= N outcomes -> schedule calibration_run; after each calibration decision -> report to user in plain language ('model changed because ...' or 'model unchanged because it did not beat the current version').
  learning ledger: monotone log of model version changes and their measured effects on out-of-sample error; rendered in the UI as 'Is the twin getting better?'
TESTS: error attribution on synthetic case where only weather differs -> residual error ~0; PIT uniform for a calibrated synthetic model.
"""
