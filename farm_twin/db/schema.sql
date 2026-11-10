-- FILE: farm_twin/db/schema.sql
-- PURPOSE: PostgreSQL 16 + PostGIS DDL. Codex: implement via Alembic migrations (this file is the design of record).
-- RULE: observation / estimate / prediction are SEPARATE tables (provenance rule in CONVENTIONS.md).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE property (
  id uuid PRIMARY KEY, name text NOT NULL, owner_id text, country_iso char(2) NOT NULL, region_code text, tz text NOT NULL DEFAULT 'Asia/Kolkata',
  ref_point geometry(Point,4326) NOT NULL, local_epsg int NOT NULL, currency char(3) NOT NULL DEFAULT 'INR',
  land_unit_factors jsonb NOT NULL DEFAULT '{}', created_at timestamptz DEFAULT now());

CREATE TABLE plot (
  id uuid PRIMARY KEY, property_id uuid REFERENCES property(id) ON DELETE CASCADE, name text NOT NULL,
  geom geometry(Polygon,4326) NOT NULL, area_m2 double precision NOT NULL CHECK (area_m2 > 0),
  eligible_uses text[] NOT NULL, land_use text NOT NULL, elevation_m double precision, slope_deg double precision, aspect_deg double precision,
  UNIQUE(property_id, name));
CREATE INDEX plot_geom_gix ON plot USING gist(geom);

CREATE TABLE variable_def (          -- registry of every observable/state variable
  code text PRIMARY KEY, label text, canonical_unit text NOT NULL, min_valid double precision, max_valid double precision, domain text);

CREATE TABLE dataset (               -- every upload / provider pull is a dataset with a content hash
  id uuid PRIMARY KEY, kind text, provider text, uri text, content_sha256 text, license text, retrieved_at timestamptz,
  spatial_extent geometry(Polygon,4326), time_start timestamptz, time_end timestamptz, meta jsonb);

CREATE TABLE scenario (
  id uuid PRIMARY KEY, property_id uuid NOT NULL REFERENCES property(id) ON DELETE CASCADE,
  owner_id text NOT NULL, name text NOT NULL, config jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX scenario_property_owner_idx ON scenario(property_id, owner_id);
CREATE TABLE api_idempotency (
  tenant_id text NOT NULL, key text NOT NULL, operation text NOT NULL, request_hash text NOT NULL,
  response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,key));
CREATE TABLE async_job (
  id uuid PRIMARY KEY, tenant_id text NOT NULL, kind text NOT NULL, payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  idempotency_key text, request_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz,
  lease_expires_at timestamptz, finished_at timestamptz, attempts int NOT NULL DEFAULT 0 CHECK(attempts >= 0), result jsonb, error jsonb,
  UNIQUE(tenant_id,kind,idempotency_key));
CREATE INDEX async_job_queue_idx ON async_job(created_at,id) WHERE status='QUEUED';

CREATE TABLE observation (           -- MEASURED / IMPORTED only
  id uuid PRIMARY KEY, plot_id uuid REFERENCES plot(id), property_id uuid REFERENCES property(id),
  variable text REFERENCES variable_def(code), depth_top_m double precision, depth_bottom_m double precision,
  observed_at timestamptz NOT NULL, value double precision NOT NULL, unit text NOT NULL, source text CHECK (source IN ('MEASURED','IMPORTED')),
  method text, dataset_id uuid REFERENCES dataset(id), uncertainty_sd double precision, quality_flags text[] DEFAULT '{}',
  superseded_by uuid REFERENCES observation(id), UNIQUE (plot_id, variable, depth_top_m, depth_bottom_m, observed_at, dataset_id));
CREATE INDEX obs_plot_var_t ON observation(plot_id, variable, observed_at);

CREATE TABLE estimate (              -- ESTIMATED values (gap fills, pedotransfer, regional priors)
  id uuid PRIMARY KEY, plot_id uuid, variable text, depth_top_m double precision, depth_bottom_m double precision, valid_at timestamptz,
  value double precision NOT NULL, unit text NOT NULL, method text NOT NULL, uncertainty_sd double precision NOT NULL, parent_ids uuid[] NOT NULL);

CREATE TABLE parameter_set (         -- versioned model parameters at 4 hierarchy levels
  id uuid PRIMARY KEY, model text NOT NULL, model_version text NOT NULL, level text CHECK (level IN ('GENERIC','REGIONAL','FARM','PLOT')),
  scope_id uuid, parent_set_id uuid REFERENCES parameter_set(id), params jsonb NOT NULL, posterior jsonb, status text CHECK (status IN ('CANDIDATE','VALIDATED','REJECTED','ACTIVE','RETIRED')),
  created_at timestamptz DEFAULT now(), promoted_at timestamptz, validation_report_id uuid);

CREATE TABLE sim_run (               -- reproducibility record for EVERY simulation
  id uuid PRIMARY KEY, scenario_id uuid, started_at timestamptz, finished_at timestamptz, config jsonb NOT NULL, config_hash text NOT NULL,
  input_hash text NOT NULL, rng_seed bigint NOT NULL, model_versions jsonb NOT NULL, parameter_set_ids jsonb NOT NULL, code_git_sha text, status text, error jsonb);

CREATE TABLE prediction (            -- MODEL_PREDICTED
  id uuid PRIMARY KEY, sim_run_id uuid REFERENCES sim_run(id), plot_id uuid, variable text, valid_at timestamptz, depth_top_m double precision, depth_bottom_m double precision,
  mean double precision, sd double precision, q05 double precision, q50 double precision, q95 double precision, unit text);

CREATE TABLE state_delta (id uuid PRIMARY KEY, sim_run_id uuid, state_date date, parent_state_id uuid, delta jsonb NOT NULL, is_snapshot boolean DEFAULT false);

CREATE TABLE intervention (          -- recommendation -> approval -> execution -> outcome chain
  id uuid PRIMARY KEY, plot_id uuid, kind text NOT NULL, payload jsonb NOT NULL, proposed_by text NOT NULL, status text NOT NULL,
  recommendation_id uuid, approval_id uuid, planned_date date, executed_date date, actual_payload jsonb);
CREATE TABLE recommendation (
  id uuid PRIMARY KEY, created_at timestamptz DEFAULT now(), scenario_id uuid, sim_run_id uuid, summary text, expected jsonb NOT NULL, -- expected KPIs with distributions
  evidence_refs jsonb NOT NULL, assumptions jsonb NOT NULL, status text);
CREATE TABLE approval (id uuid PRIMARY KEY, recommendation_id uuid, decided_by text NOT NULL, decision text CHECK (decision IN ('APPROVED','REJECTED','MODIFIED')), note text, decided_at timestamptz DEFAULT now(), token_hash text);
CREATE TABLE outcome (id uuid PRIMARY KEY, intervention_id uuid, variable text, observed_at timestamptz, value double precision, unit text, prediction_id uuid, error double precision);

CREATE TABLE event_outbox (
  id uuid PRIMARY KEY,
  event_id text UNIQUE NOT NULL,
  event_type text NOT NULL,
  plot_id uuid REFERENCES plot(id) ON DELETE SET NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  delivered_at timestamptz
);
CREATE INDEX event_outbox_pending_idx ON event_outbox(created_at) WHERE delivered_at IS NULL;

CREATE TABLE calibration_run (id uuid PRIMARY KEY, model text, level text, scope_id uuid, method text, data_window tstzrange, n_obs int, train_idx jsonb, holdout_idx jsonb, metrics_before jsonb, metrics_after jsonb, decision text, reason text, candidate_set_id uuid, created_at timestamptz DEFAULT now());
CREATE TABLE agent_run (id uuid PRIMARY KEY, thread_id text, started_at timestamptz, user_request text, graph_version text, status text);
CREATE TABLE tool_call (id uuid PRIMARY KEY, agent_run_id uuid, agent text, tool text, args jsonb, result_summary jsonb, result_hash text, ok boolean, error jsonb, started_at timestamptz, duration_ms int, approval_id uuid);
CREATE TABLE audit_log (id bigserial PRIMARY KEY, at timestamptz DEFAULT now(), actor text, action text, entity text, entity_id uuid, before jsonb, after jsonb);
CREATE TABLE price_observation (id uuid PRIMARY KEY, commodity text, market text, observed_on date, modal_price_inr_per_quintal double precision, min_price double precision, max_price double precision, arrivals_t double precision, dataset_id uuid);
CREATE TABLE weather_daily (id bigserial PRIMARY KEY, location_id uuid, date date, tmax double precision, tmin double precision, rain_mm double precision, rs_mj_m2 double precision, rh_mean double precision, u2_ms double precision, et0_mm double precision, provider text, is_forecast boolean, retrieved_at timestamptz, UNIQUE(location_id,date,provider,is_forecast));
CREATE TABLE sat_scene (id uuid PRIMARY KEY, plot_id uuid, scene_id text, acquired_at timestamptz, cloud_pct double precision, ndvi_mean double precision, ndvi_sd double precision, evi_mean double precision, n_valid_pixels int, valid_frac double precision, dataset_id uuid);
-- Codex: also create views v_latest_soil_by_plot, v_prediction_vs_outcome (join prediction/outcome), and enforce with triggers that observation.source <> 'MODEL_PREDICTED'.

CREATE OR REPLACE FUNCTION enforce_observation_append_only() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'observations are append-only; supersede with a correction row';
  END IF;
  IF (to_jsonb(NEW) - 'superseded_by') <> (to_jsonb(OLD) - 'superseded_by')
     OR OLD.superseded_by IS NOT NULL OR NEW.superseded_by IS NULL THEN
    RAISE EXCEPTION 'observation may only be superseded once; data fields cannot be updated';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER observation_append_only BEFORE UPDATE OR DELETE ON observation
  FOR EACH ROW EXECUTE FUNCTION enforce_observation_append_only();

CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

CREATE OR REPLACE VIEW v_latest_soil_by_plot AS
SELECT DISTINCT ON (o.plot_id, o.variable, o.depth_top_m, o.depth_bottom_m)
  o.plot_id, o.variable, o.depth_top_m, o.depth_bottom_m, o.value, o.unit, o.source,
  o.method, o.dataset_id, o.observed_at, o.quality_flags
FROM observation o
JOIN variable_def v ON v.code = o.variable
WHERE v.domain = 'soil' AND o.superseded_by IS NULL
ORDER BY o.plot_id, o.variable, o.depth_top_m, o.depth_bottom_m, o.observed_at DESC;

CREATE OR REPLACE VIEW v_prediction_vs_outcome AS
SELECT p.id AS prediction_id, p.sim_run_id, p.plot_id, p.variable,
  p.valid_at, p.mean AS predicted_mean, o.value AS observed_value, o.error,
  o.observed_at, o.unit
FROM prediction p JOIN outcome o ON o.prediction_id = p.id;
