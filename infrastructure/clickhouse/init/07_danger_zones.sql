-- ============================================================================
-- Load sample danger zones for carros fiber
--
-- Data based on real A8 highway features near Nice, France
-- Coordinates estimated for demonstration purposes
-- ============================================================================

-- Clear existing danger zones (idempotent)
-- Note: Using ReplacingMergeTree, newer rows replace older ones with same ORDER BY key
TRUNCATE TABLE IF EXISTS sequoia.fiber_danger_zones;

-- Tunnel de Carros (A8 autoroute)
-- Real tunnel on A8 near Nice
INSERT INTO sequoia.fiber_danger_zones (
    zone_id,
    fiber_id,
    zone_type,
    zone_name,
    description,
    channel_start,
    channel_end,
    pk_start,
    pk_fin,
    severite_boost,
    contexte_boost,
    is_active,
    created_at,
    updated_at
) VALUES (
    'ZONE-TUNNEL-CARROS-001',
    'carros',
    'tunnel',
    'Tunnel de Carros',
    'Tunnel urbain 850m - A8 autoroute. Pas de bande d''arrêt d''urgence, éclairage artificiel, ventilation. Tout incident est critique.',
    1200,  -- channel_start
    1350,  -- channel_end (150 channels ≈ 850m)
    145.2, -- pk_start
    145.8, -- pk_fin
    1.5,   -- +50% severity boost (no escape, confined space)
    1.3,   -- +30% context boost (visibility issues, ventilation)
    1,     -- active
    now(),
    now()
);

-- Viaduc de la Siagne (A8 autoroute)
-- Bridge crossing the Siagne river
INSERT INTO sequoia.fiber_danger_zones (
    zone_id,
    fiber_id,
    zone_type,
    zone_name,
    description,
    channel_start,
    channel_end,
    pk_start,
    pk_fin,
    severite_boost,
    contexte_boost,
    is_active,
    created_at,
    updated_at
) VALUES (
    'ZONE-BRIDGE-SIAGNE-001',
    'carros',
    'bridge',
    'Viaduc de la Siagne',
    'Viaduc hauteur 45m au-dessus de la Siagne. Pas de bande d''arrêt d''urgence, vent latéral possible.',
    2100,  -- channel_start
    2150,  -- channel_end (50 channels ≈ 280m)
    152.3, -- pk_start
    152.5, -- pk_fin
    1.3,   -- +30% severity boost (no escape, height hazard)
    1.2,   -- +20% context boost (wind, weather sensitivity)
    1,     -- active
    now(),
    now()
);

-- Intersection A8/A57 (Autoroute merge)
-- High-traffic junction point
INSERT INTO sequoia.fiber_danger_zones (
    zone_id,
    fiber_id,
    zone_type,
    zone_name,
    description,
    channel_start,
    channel_end,
    pk_start,
    pk_fin,
    severite_boost,
    contexte_boost,
    is_active,
    created_at,
    updated_at
) VALUES (
    'ZONE-INTERSECTION-A8A57-001',
    'carros',
    'intersection',
    'Échangeur A8/A57',
    'Zone de convergence A8/A57. Fort trafic, changements de voie fréquents, confusion possible.',
    3500,  -- channel_start
    3600,  -- channel_end (100 channels ≈ 550m)
    158.5, -- pk_start
    159.0, -- pk_fin
    1.2,   -- +20% severity boost (merge conflicts)
    1.4,   -- +40% context boost (complexity, confusion)
    1,     -- active
    now(),
    now()
);

-- Zone urbaine dense (Antibes city section)
-- Urban highway section with high traffic density
INSERT INTO sequoia.fiber_danger_zones (
    zone_id,
    fiber_id,
    zone_type,
    zone_name,
    description,
    channel_start,
    channel_end,
    pk_start,
    pk_fin,
    severite_boost,
    contexte_boost,
    is_active,
    created_at,
    updated_at
) VALUES (
    'ZONE-URBAN-ANTIBES-001',
    'carros',
    'urban_dense',
    'Traversée Antibes',
    'Section urbaine dense. Trafic élevé aux heures de pointe, nombreux accès, vitesse réduite.',
    4200,  -- channel_start
    4500,  -- channel_end (300 channels ≈ 1.7km)
    162.0, -- pk_start
    163.7, -- pk_fin
    1.1,   -- +10% severity boost (urban hazards)
    1.5,   -- +50% context boost (rush hour impact)
    1,     -- active
    now(),
    now()
);

-- Verify insertion
SELECT
    zone_id,
    zone_type,
    zone_name,
    concat('Ch ', toString(channel_start), '-', toString(channel_end)) as channels,
    concat('PK ', toString(pk_start), '-', toString(pk_fin)) as pk_range,
    concat('+', toString((severite_boost - 1) * 100), '%') as severity_boost_pct,
    is_active
FROM sequoia.fiber_danger_zones
ORDER BY channel_start;
