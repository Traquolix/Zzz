# Incident Replay Player

## Goal

Build an interactive incident replay view inside the side panel. When you open an incident, you see a chart of the full 2-minute window (±60s around detection time) with the incident marked at the center. Below the chart, a playback slider scrubs through time. Below that, a small embedded map replays what was happening on the road — with the same visualization modes as the main PrototypeMap (dots or 3D vehicles). Scrubbing the slider updates the chart cursor, the mini map, and the stats together.

Snapshots are stored persistently so any past incident can be replayed.

## Visual layout

All inside the incident detail view in the side panel:

```
+-----------------------------------------------+
|  Incident header (type, severity, location)    |
+-----------------------------------------------+
|                                                |
|  SNAPSHOT CHART (speed over time, full 2 min)  |
|                                                |
|  ····|····|····|···↕···|····|····|····|····    |
|                    ^                           |
|           incident marker (dashed vertical)    |
|           always centered in the window        |
|                    |                           |
|  ·····────────────●┤····  ← playback cursor    |
|                                                |
+-----------------------------------------------+
|  ▶ ▮▮  1x  [=======●=========]  -0:32 / 2:00 |
|         playback slider (scrubs chart + map)   |
+-----------------------------------------------+
|  ┌─────────────────────────────────────────┐   |
|  │  [Dots] [3D]              mini map      │   |
|  │                                         │   |
|  │   Zoomed to ±100 channels around        │   |
|  │   incident. Detections rendered as      │   |
|  │   dots or 3D vehicles (same modes as    │   |
|  │   the main map). Color-coded by speed.  │   |
|  │                                         │   |
|  └─────────────────────────────────────────┘   |
+-----------------------------------------------+
|  Avg speed: 45 km/h  |  Flow: 12 veh  |  ... |
+-----------------------------------------------+
```

## Behavior

### Chart
- Always shows the **full 2-minute window** (detected_at ± 60s)
- **Incident marker** — dashed vertical line at detection time, always centered
- **Playback cursor** — solid vertical line that follows the slider
- When still collecting (`complete: false`), left half populated immediately, right half fills progressively

### Slider
- Between chart and mini map
- Range = full 2 minutes, draggable, updates chart cursor + map + stats
- Transport: play/pause, speed (0.5x, 1x, 2x, 4x)
- Relative time display (`-0:32`, `+0:15`)
- Scrub backward and forward freely

### Mini map
- Small self-contained Mapbox GL instance (~200px tall) in the side panel
- Separate from the main full-screen map
- Auto-zoomed to ±100 channels around the incident
- Shows the fiber path as a line
- **Same visualization modes as PrototypeMap**: toggle between channel dots and 3D vehicle models. Uses the same rendering code/layers.
- Detections rendered at channel positions for the current playback second
- Color-coded by speed (green → yellow → red)
- As you scrub: vehicles/dots move along the fiber, slow near the incident, traffic builds up
- Static camera centered on incident, minimal chrome

### Progressive collection
- Left half appears immediately (pre-incident data from rolling buffer)
- Right half fills second by second
- "Collecting..." indicator until `complete: true`
- Slider works on available data immediately

## Data recording

### What gets recorded
All detections within **±100 channels** of the incident center, for the full 2-minute window. Captures vehicles approaching from both directions and leaving.

### Rolling buffer (pre-incident)
Per-fiber rolling buffer of last 60s of all detections. On incident spawn, the ±100 channel slice seeds the snapshot's first half.

### Live recording (post-incident)
New detections within ±100 channels appended until detected_at + 60s, then marked `complete`.

### Persistent storage
- **Simulation**: completed snapshots saved via Django ORM or file storage for replay after restart
- **Production**: ClickHouse `detection_hires` (48h TTL) already stores raw detections — queried directly. For older incidents, `detection_1m` for lower-res replay.

### Parameters
- `SNAPSHOT_CHANNEL_RADIUS = 100` — ±100 channels (~1km)
- `SNAPSHOT_WINDOW_S = 60` — ±60s (2 minutes total)
- `SNAPSHOT_MAX_DETECTIONS = 20000`

## Phases

### Phase 1 — Playback slider + chart cursor
- Incident vertical marker on chart already implemented (dashed red line at incident time)
- Playback cursor on chart (follows slider)
- `useSnapshotPlayback` hook (currentMs, playing, speed, seek)
- `SnapshotPlayer` component (slider + play/pause/speed)
- Widen snapshot recording to ±100 channels, raise cap

### Phase 2 — Embedded mini map
- Small Mapbox GL instance in side panel (~200px, minimal chrome)
- Fiber path line in incident area
- Detection rendering with **both modes**: dots and 3D vehicles (reuse PrototypeMap layer code)
- Toggle between modes (small [Dots] [3D] toggle in corner)
- Color-code by speed, static camera on incident

### Phase 3 — Persistent storage
- Save completed sim snapshots to DB/file
- Load for past incident replay
- ClickHouse path already works for production

### Phase 4 — Polish
- Stats row (speed, flow, count at cursor)
- Keyboard shortcuts (space = play/pause, arrows = ±1s)
- Smooth interpolation between seconds
- Lower-res replay for incidents older than 48h
