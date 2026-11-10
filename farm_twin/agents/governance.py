"""
FILE: farm_twin/agents/governance.py
PURPOSE: Approval workflow, permissions, audit trail.

IMPLEMENT: ApprovalRequest(id, recommendation_id, summary_plain, expected_kpis (distributions), top_risks, assumptions, data_gaps, reversible: bool, estimated_cost_inr, expires_at). request_approval(...) -> calls langgraph interrupt(payload) and resumes with {decision, note, modifications}. Token: on APPROVED create `approval` row + opaque token (HMAC) required by gated tools; tokens are single-use, bound to (recommendation_id, tool name, args hash), expire (default 7 days).
 Permission model (RBAC): FARMER (approve own farm), AGRONOMIST_ADVISOR (propose, comment), VIEWER, ADMIN (model changes); actions: promote_params (only gate or ADMIN), delete_data (never; supersede only), change_active_plan (FARMER).
 Hard prohibitions encoded as policy checks: agents cannot (i) alter MEASURED observations, (ii) promote calibration sets, (iii) execute purchases/payments/external actions, (iv) hide warnings flagged `must_show`.
 audit_log append-only (DB trigger forbids UPDATE/DELETE).
TESTS: token single use; expired token rejected; tool without token raises ApprovalRequiredError; audit immutability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import secrets
from typing import Any

from farm_twin.core.errors import ApprovalRequiredError


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    recommendation_id: str
    summary_plain: str
    expires_at: datetime


class ApprovalAuthority:
    """Process-local, single-use approval token authority; durable storage is not yet wired."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("approval secret must contain at least 32 bytes")
        self._secret = secret
        self._used: set[str] = set()
        self.audit_log: list[dict[str, Any]] = []

    def issue(self, recommendation_id: str, tool: str, args: dict[str, Any], now: datetime | None = None) -> str:
        timestamp = now or datetime.now(timezone.utc)
        exp = timestamp + timedelta(days=7)
        nonce = secrets.token_urlsafe(24)
        body = f"{recommendation_id}|{tool}|{sha256(repr(sorted(args.items())).encode()).hexdigest()}|{int(exp.timestamp())}|{nonce}"
        sig = hmac.new(self._secret, body.encode(), "sha256").hexdigest()
        token = body + "|" + sig
        self.audit_log.append(
            {"action": "ISSUE", "recommendation_id": recommendation_id, "tool": tool, "at": timestamp.isoformat()}
        )
        return token

    def consume(
        self, token: str, recommendation_id: str, tool: str, args: dict[str, Any], now: datetime | None = None
    ) -> None:
        try:
            rid, tname, ahash, expiry, nonce, sig = token.split("|")
        except ValueError as exc:
            raise ApprovalRequiredError("malformed approval token") from exc
        body = "|".join((rid, tname, ahash, expiry, nonce))
        expected = hmac.new(self._secret, body.encode(), "sha256").hexdigest()
        current = now or datetime.now(timezone.utc)
        token_id = sha256(token.encode()).hexdigest()
        valid = (
            hmac.compare_digest(sig, expected)
            and rid == recommendation_id
            and tname == tool
            and ahash == sha256(repr(sorted(args.items())).encode()).hexdigest()
            and current.timestamp() <= int(expiry)
            and token_id not in self._used
        )
        if not valid:
            raise ApprovalRequiredError("approval token invalid, expired, mismatched, or already used")
        self._used.add(token_id)
        self.audit_log.append({"action": "CONSUME", "recommendation_id": rid, "tool": tname, "at": current.isoformat()})
