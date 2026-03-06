# Incident Replay Player

## Goal

Build an interactive incident replay view that lets users scrub through the ±60s snapshot window around an incident, seeing detection data animate on the map and charts simultaneously. This turns a static snapshot into a forensic tool for understanding how an incident developed.

## What it looks like

When viewing an incident in the side panel, below the current snapshot chart:

- **Time slider** spanning the full snapshot window (detected_at - 60s to detected_at + 60s)
- **Play/pause button** with adjustable speed (0.5x, 1x, 2x, 4x)
- **Map view** zoomed to the incident area showing detection dots at channel positions, color-coded by speed (green = normal, yellow = slowing, red = stopped), filtered to the current playback second
- **Chart cursor** — a vertical line on the TimeSeriesChart that tracks the playback position
- **Stats at cursor** — speed, flow, vehicle count at the current playback time

As the user scrubs or plays, all views update together: dots appear/disappear on the map, the chart cursor moves, and stats update. You can literally watch the speed drop propagate along the fiber as the incident develops.

While the snapshot is still collecting (`complete: false`), the slider range extends as new data arrives.

## Existing pieces

- Snapshot detections already include channel positions and timestamps at per-second granularity
- Fiber coordinates are mapped to lat/lng (`channel_coordinates` in cable data) — channel index maps to a map position
- PrototypeMap already has a channel helper dots layer that renders circles at channel positions
- TimeSeriesChart component renders the speed/flow/occupancy chart
- Snapshot polling (1s) already keeps data fresh while collecting

## Implementation sketch

### 1. Shared playback state

```typescript
type PlaybackState = {
  currentMs: number       // Current playback timestamp (ms)
  playing: boolean
  speed: number           // 0.5 | 1 | 2 | 4
  startMs: number         // Snapshot window start
  endMs: number           // Snapshot window end
}
```

A `useSnapshotPlayback` hook that manages this state, advances `currentMs` via `requestAnimationFrame` when playing, and exposes `play()`, `pause()`, `seek(ms)`, `setSpeed()`.

### 2. SnapshotPlayer component

Transport controls + time slider. Sits between the incident header and the chart. Shows elapsed time and total duration. The slider is draggable for manual scrubbing.

### 3. Map incident layer

A new Mapbox source/layer that:
- Filters snapshot detections to the current playback second (±500ms window)
- Maps each detection's channel to a lat/lng via the fiber's `channel_coordinates`
- Renders as circles, sized by vehicle count, colored by speed relative to the section's speed thresholds
- Zooms/fits the map to the incident area (center channel ± radius) when the player activates

### 4. Chart cursor overlay

Add an optional `cursorX` prop to TimeSeriesChart that renders a vertical line at the corresponding time position. The playback state drives this.

### 5. Stats panel

Small row below the chart showing interpolated values at the cursor position: avg speed, total flow, vehicle count. Updates as cursor moves.

## Phases

### Phase 1 — Playback controls + chart cursor
- `useSnapshotPlayback` hook
- `SnapshotPlayer` component (slider + play/pause/speed)
- Chart cursor overlay
- No map changes yet — just the time controls and chart interaction

### Phase 2 — Map visualization
- Incident detection dots layer on the map
- Channel-to-coordinate mapping for the incident's fiber
- Color-coding by speed
- Auto-zoom to incident area

### Phase 3 — Polish
- Stats at cursor
- Keyboard shortcuts (space = play/pause, arrow keys = step ±1s)
- Smooth dot transitions between seconds (interpolation)
- Loading state while snapshot collects
