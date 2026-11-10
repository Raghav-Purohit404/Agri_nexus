"""P09-P16 pure contract tests; runtime execution requires the project's Python 3.11 extras."""

import numpy as np
import pytest
from farm_twin.state.coupling import Edge, CouplingCycleError, topological_order
from farm_twin.uncertainty.sensitivity import ishigami
from farm_twin.optimization.milp_cvar import lower_cvar, solve_enumerated
from farm_twin.voi.value_of_information import evpi
from farm_twin.calibration.promotion_gate import evaluate_candidate
from farm_twin.agents.evals import groundedness


def test_lagged_coupling_breaks_cycle():
    edges = [Edge("a", "x", "b", "x"), Edge("b", "x", "a", "x", lag_days=1)]
    assert set(topological_order(edges, ["a", "b"])) == {"a", "b"}


def test_unlagged_coupling_cycle_rejected():
    with pytest.raises(CouplingCycleError):
        topological_order([Edge("a", "x", "b", "x"), Edge("b", "x", "a", "x")], ["a", "b"])


def test_lower_cvar_uses_worst_tail():
    assert lower_cvar(np.array([-10.0, 0.0, 10.0, 20.0, 30.0]), 0.8) == pytest.approx(-10.0)


def test_risk_neutral_enumerated_allocation():
    payoff = np.array([[[10.0, 0.0], [6.0, 6.0]]])
    capex = np.array([[0.0, 0.0]])
    result = solve_enumerated(payoff, capex, 1.0, alpha=0.5, risk_lambda=0.0)
    assert result.option_indices == (1,)


def test_evpi_zero_for_dominant_decision():
    u = np.array([[5.0, 6.0, 4.0], [1.0, 2.0, 3.0]])
    assert evpi(u) == pytest.approx(0.0)


def test_calibration_rejects_worse_candidate():
    d = evaluate_candidate({"yield": 1.0}, {"yield": 1.1}, {"yield": 2.0}, {"yield": 2.0}, 0.9, 3, 10, True, 1.0)
    assert not d.promote


def test_groundedness_rejects_unsupported_number():
    assert groundedness("Yield is 12.5 t/ha", [{"yield": 10.0}])["score"] == 0.0


def test_ishigami_smoke_is_finite():
    assert np.isfinite(ishigami(np.array([0.2, 0.4, 0.6])))
