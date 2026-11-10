# Project Definition

## Objective
Given a property (plots of arbitrary size/shape), its soil, water, climate, capital and goals, build a **probabilistic digital twin** that (1) represents current state with explicit provenance, (2) simulates soil, water, crop, solar, agrivoltaic and financial futures under uncertainty, (3) recommends land-use / crop / irrigation / amendment / PV decisions that are optimal under risk, (4) learns from outcomes only when it provably improves, and (5) is operated through governed AI agents with human approval.

## Pilot context
Arid NW India (Jodhpur-type climate), three plots of 800, 600 and 1300 sq ft (74.3, 55.7, 120.8 m2); user supplies soil/water data; Plot C may be reserved for PV/agrivoltaics. At this scale a plot is smaller than a Sentinel-2 10 m pixel block, kWp values are single-digit, and crop yield per plot is kilograms - economics are driven by water, labour and capex, not field-scale yield.

## Non-goals
Not a replacement for an agronomist/electrician; no electrical design sign-off; no carbon-credit verification; no automatic purchases; no pest/disease forecasting at Level 1; no perennial/tree crops at Level 1.

## Success criteria
- Reproduces reference crop-model regression data (yield +/-3 %, irrigation +/-5 mm).
- All mass balances (water, salt, N, C) close within stated tolerances in every run.
- Every number shown carries unit, uncertainty and provenance.
- Calibration never degrades held-out accuracy (promotion gate) and can roll back.
- Agents are grounded: >= 98 % of stated numbers trace to tool evidence; 100 % refusal on forbidden actions.
