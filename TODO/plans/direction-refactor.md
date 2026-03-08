# Direction Refactor — Make Direction a First-Class Field [#58]

## Goal

Stop encoding direction in fiber_id strings (`"carros:0"`). Make `direction` a
separate field everywhere: ClickHouse columns, WebSocket messages, REST responses,
frontend types, simulation dataclasses.

## New Data Shapes

### WebSocket Detection
```json
// BEFORE: { "fiberLine": "carros:0", "channel": 42, "speed": 87.3, "direction": 0, ... }
// AFTER:  { "fiberId": "carros", "direction": 0, "channel": 42, "speed": 87.3, ... }
```

### WebSocket Incident
```json
// BEFORE: { "id": "inc-...", "fiberLine": "carros:0", "channel": 120, ... }
// AFTER:  { "id": "inc-...", "fiberId": "carros", "direction": 0, "channel": 120, ... }
```

### WebSocket VehicleCount
```json
// BEFORE: { "fiberLine": "carros:0", "channelStart": 0, "channelEnd": 299, ... }
// AFTER:  { "fiberId": "carros", "direction": 0, "channelStart": 0, "channelEnd": 299, ... }
```

### REST Section
```json
// BEFORE: { "fiberId": "carros:0", "channelStart": 100, "channelEnd": 200, ... }
// AFTER:  { "fiberId": "carros", "direction": 0, "channelStart": 100, "channelEnd": 200, ... }
```

## ClickHouse Migration

- Add `direction UInt8 DEFAULT 0` to `fiber_incidents`, `fiber_monitored_sections`, `fiber_danger_zones`
- Backfill `fiber_monitored_sections`: parse `"carros:0"` → `fiber_id="carros"`, `direction=0`
- Safe to run before code deploy (existing code ignores new column)

## Implementation Order

1. ClickHouse migration SQL
2. Backend: incident_service (core transforms, delete helpers)
3. Backend: broadcast layer (routing simplification)
4. Backend: kafka bridge (detection/incident emit)
5. Backend: simulation engine (Incident dataclass, buffer keys, broadcasts)
6. Backend: fiber utils (org-scoped filtering)
7. Backend: monitoring views (snapshots, sections)
8. Backend: section service (queries, insert)
9. Backend: export views
10. Backend: alerting (evaluator, integration)
11. Backend: admin API (test payload)
12. Frontend: types (Detection, VehicleCount, Incident)
13. Frontend: parseMessage (type guards)
14. Frontend: data/utility layer (coordinate lookup)
15. Frontend: hooks (detections, live stats, waterfall, sections)
16. Frontend: components (map, side panel)

## Frontend Coordinate Lookup

The combined `"carros:0"` is still needed for coordinate lookups (fiber array
is indexed by directional ID). A thin helper constructs it from separate fields:

```typescript
function directionalId(fiberId: string, direction: 0 | 1): string {
  return `${fiberId}:${direction}`
}
```

This replaces `resolveDirectionalFiber()` but is explicit (both fields known)
rather than guessing (defaulting direction to 0).

## Code Deletions

- `_ensure_directional_fiber_id()` — incident_service.py
- `strip_directional_suffix()` — incident_service.py
- `parse_directional_fiber_id()` — incident_service.py
- `_strip_directional_suffix()` — broadcast.py
- `resolveDirectionalFiber()` — data.ts
- Section expansion logic (`f"{fid}:0"`, `f"{fid}:1"`) — section_service.py
