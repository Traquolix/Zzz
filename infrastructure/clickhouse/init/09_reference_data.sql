-- ============================================================================
-- Reference Data - Actors and Monitored Sections
-- ============================================================================

-- Default actors
INSERT INTO sequoia.actors (actor_id, actor_name, actor_role, contact_info, is_active, created_at, updated_at)
VALUES
    ('actor-default-operator', 'Default Operator', 'operator', 'operator@sequoia.com', 1, now(), now()),
    ('actor-default-technician', 'Field Technician', 'technician', '+33 6 12 34 56 78', 1, now(), now());

-- Default monitored sections
INSERT INTO sequoia.fiber_monitored_sections (
    section_id, fiber_id, section_name, channel_start, channel_end,
    expected_travel_time_seconds, alert_threshold_percent, is_active,
    created_at, created_by, updated_at
) VALUES
    ('section-nice-center-airport', 'carros', 'Nice Centre → Airport', 5000, 8000, NULL, 30.0, 1, now(), 'actor-default-operator', now()),
    ('section-saint-jeannet-vence', 'carros', 'Saint-Jeannet → Vence', 1000, 3500, NULL, 25.0, 1, now(), 'actor-default-operator', now());

SELECT 'Reference data loaded' as status;
