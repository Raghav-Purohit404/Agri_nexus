# Test index
Every module docstring lists its own tests (TESTS:). Create them as tests/test_<module>.py. Golden data in tests/golden/. Required cross-cutting suites:
- test_mass_balance.py (water, salt, N, C closure on random 10-year runs; hypothesis)
- test_golden_crop.py, test_golden_pv.py, test_cvar_prototype.py
- test_oracle_raycast.py (3-D brute-force shading vs 2-D analytic)
- test_twin_calibration.py (parameter recovery, coverage)
- test_agent_evals.py (groundedness, refusal, injection)
