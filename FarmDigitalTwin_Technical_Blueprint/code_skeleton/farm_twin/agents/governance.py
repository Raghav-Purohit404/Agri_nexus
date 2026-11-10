"""
FILE: farm_twin/agents/governance.py
PURPOSE: Approval workflow, permissions, audit trail.

IMPLEMENT: ApprovalRequest(id, recommendation_id, summary_plain, expected_kpis (distributions), top_risks, assumptions, data_gaps, reversible: bool, estimated_cost_inr, expires_at). request_approval(...) -> calls langgraph interrupt(payload) and resumes with {decision, note, modifications}. Token: on APPROVED create `approval` row + opaque token (HMAC) required by gated tools; tokens are single-use, bound to (recommendation_id, tool name, args hash), expire (default 7 days).
 Permission model (RBAC): FARMER (approve own farm), AGRONOMIST_ADVISOR (propose, comment), VIEWER, ADMIN (model changes); actions: promote_params (only gate or ADMIN), delete_data (never; supersede only), change_active_plan (FARMER).
 Hard prohibitions encoded as policy checks: agents cannot (i) alter MEASURED observations, (ii) promote calibration sets, (iii) execute purchases/payments/external actions, (iv) hide warnings flagged `must_show`.
 audit_log append-only (DB trigger forbids UPDATE/DELETE).
TESTS: token single use; expired token rejected; tool without token raises ApprovalRequiredError; audit immutability.
"""
