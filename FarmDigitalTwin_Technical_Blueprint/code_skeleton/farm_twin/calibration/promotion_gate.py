"""
FILE: farm_twin/calibration/promotion_gate.py
PURPOSE: No calibrated parameter set is used in production unless it PROVES it predicts held-out data better than the parent set. This is the safety mechanism behind 'the model learns without degrading'.

PROCEDURE promote(candidate_set):
   1. Temporal blocked cross-validation (leave-one-season-out, never random splits - weather autocorrelation) producing out-of-sample predictions for candidate and for the current ACTIVE parent.
   2. Metrics per variable: RMSE, MAE, bias, NSE, KGE, and PROBABILISTIC: CRPS and 90 % interval coverage (should be 0.85-0.95) and PIT histogram check.
   3. Criteria (all must hold): CRPS(candidate) <= 0.95*CRPS(parent) on pooled held-out data; no variable's RMSE worsens by > 10 %; coverage within 0.80-0.97; physical-sanity checks pass (parameters in valid ranges; simulated mass balances unchanged); minimum evidence: >= 2 independent seasons or >= 8 independent observation points at that level; stability: parameters change < 3 posterior SD vs the previous promoted set unless justified.
   4. Decision logged in calibration_run(decision, reason, metrics_before/after). PROMOTE -> status VALIDATED then ACTIVE (previous ACTIVE -> RETIRED, kept for rollback). REJECT -> status REJECTED with reasons.
   5. DRIFT MONITOR (post-promotion): rolling prediction-error z-scores; if |mean z| > 2 for 3 consecutive outcomes or coverage collapses -> auto-ROLLBACK to previous ACTIVE and raise AnomalyDetected.
   6. Human override: agent cannot promote; only the gate (or a human with ApprovalToken for model changes).
TESTS: candidate trained on noise fails; genuinely better synthetic candidate passes; rollback triggers on injected bias.
"""
