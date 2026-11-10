"""
FILE: farm_twin/state/events.py
PURPOSE: Event bus + scheduler for the real-time (non-simulation) side: new observation arrives -> state update -> re-forecast -> maybe notify agents.

IMPLEMENT: Event types: ObservationAdded, WeatherForecastUpdated, SatelliteSceneIngested, InterventionExecuted, PriceUpdated, CalibrationPromoted, AnomalyDetected. In-process pub/sub (asyncio) with a durable outbox table (outbox in Postgres) for at-least-once delivery; handlers idempotent.
 Handlers: on ObservationAdded(soil) -> mark plot soil state stale-or-refreshed, trigger `hindcast_and_score`; on WeatherForecastUpdated -> recompute 14-day irrigation advice per cropped plot; on SatelliteScene -> compare model CC vs satellite fcover, create AnomalyDetected if |diff|>0.2 for two scenes; on InterventionExecuted -> update state, create Outcome tracking stub; on PriceUpdated -> invalidate cached financial results.
 Scheduler (APScheduler): daily 05:30 IST weather+forecast pull; weekly satellite pull; nightly calibration check; monthly full re-optimisation proposal (never auto-applied).
TESTS: at-least-once with idempotent handler; ordering within a plot preserved.
"""
