-- Migration 003: Drop unused columns from fiber_incidents and fiber_cables
--
-- fiber_incidents: 24 dead columns from legacy workflow, CIGT integration
-- (never built), and danger zone boosting (unused).
-- Keeps: updated_at (ReplacingMergeTree version key), status (used by backend).
--
-- fiber_cables: total_channels (redundant MATERIALIZED), created_at (never read).
-- Keeps: updated_at (ReplacingMergeTree version key).
--
-- Also drops indexes on removed columns.

-- ── fiber_incidents: legacy workflow columns ──
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS assigned_to;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS notes;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS resolved_at;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS resolution_notes;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS created_at;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS confidence;

-- ── fiber_incidents: CIGT classification (never built) ──
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS type_evenement;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS sous_type_evenement;

-- ── fiber_incidents: CIGT priority (never built) ──
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS severite_suggested;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS severite_validated;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS impact_trafic;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS contexte;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS priorite_operationnelle;

-- ── fiber_incidents: CIGT workflow (never built) ──
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS status_workflow;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS validated_by;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS validated_at;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS confirmed_at;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS intervention_started_at;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS closed_at;

-- ── fiber_incidents: public communication (never built) ──
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS message_public;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS canaux_diffusion;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS est_visible_public;

-- ── fiber_incidents: danger zone context (unused) ──
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS in_danger_zone;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS danger_zone_id;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS danger_zone_name;

-- ── fiber_incidents: drop indexes on removed columns ──
ALTER TABLE sequoia.fiber_incidents DROP INDEX IF EXISTS idx_workflow;
ALTER TABLE sequoia.fiber_incidents DROP INDEX IF EXISTS idx_danger_zone;

-- ── fiber_cables: unused columns ──
ALTER TABLE sequoia.fiber_cables DROP COLUMN IF EXISTS total_channels;
ALTER TABLE sequoia.fiber_cables DROP COLUMN IF EXISTS created_at;
