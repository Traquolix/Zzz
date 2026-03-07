# Simulation Engine Overhaul

## Goal

Replace the current random-event simulation with a physically coherent traffic simulation where incidents **emerge from vehicle behavior**, not from random number generators. The simulation should be indistinguishable from real DAS data at a glance: realistic speeds for each road segment, time-of-day traffic patterns matching Nice, and incident snapshots that show a genuine speed drop caused by an actual obstruction.

## Problems with the current simulation

1. **Incidents are randomly injected** — they don't arise from vehicle interactions. A "slowdown" incident appears, vehicles near it slow down, but the causality is backwards: the incident creates the slowdown, instead of a slowdown triggering incident detection.

2. **No per-road speed calibration** — all fibers use the same speed profiles. The D6202 (Carros) is a 2×2 urban highway at 70-90 km/h, the Route de Turin (Mathis) is a 50 km/h urban road, and the Promenade des Anglais is 50 km/h coastal. These should have distinct speed distributions.

3. **Time-of-day patterns are generic** — the `DAILY_TRAFFIC` array is a rough bell curve. Real Nice traffic has a sharp morning peak (7:30-9:00), a lunch dip, a long afternoon peak (16:30-19:00), and near-zero overnight. Each road has different peak hours.

4. **Incident snapshots are incoherent** — since incidents are injected rather than detected, the snapshot shows vehicles slowing down *because* an incident was declared, rather than showing the speed anomaly that *caused* the detection.

5. **No incident detection logic** — there's no speed-drop detector, no congestion detector, no anomaly classifier. The simulation should run the same (simplified) detection logic that the real pipeline uses.

## Architecture

```
Vehicle Simulation (physics)
    ↓ produces detections every tick
Incident Overseer (monitors speed/flow)
    ↓ detects anomalies → declares incidents
Snapshot Recorder (captures ±60s window)
    ↓ feeds frontend via REST/WS
```

The key change: the **Overseer** sits between the vehicle sim and the incident list. It watches aggregated speed and flow metrics per section/channel-range and triggers incidents when thresholds are crossed. Vehicles don't know about incidents directly — they react to road conditions (stopped vehicle ahead, lane blockage).

## Phase 1 — Per-road calibration

### Speed profiles per fiber

Add to `fibers.yaml` or a new `simulation.yaml`:

```yaml
fibers:
  carros:
    speed_limit: 90        # D6202, 2×2 voies
    typical_speed: [75, 85] # [min_typical, max_typical] in free flow
    lanes: 4
    peak_hours:
      morning: [7.5, 9.0]   # 7:30-9:00
      evening: [16.5, 19.0]  # 16:30-19:00
    traffic_density: high

  mathis:
    speed_limit: 50
    typical_speed: [35, 50]
    lanes: 2
    peak_hours:
      morning: [7.5, 9.0]
      evening: [17.0, 19.5]
    traffic_density: medium

  promenade:
    speed_limit: 50
    typical_speed: [30, 50]
    lanes: 4
    peak_hours:
      morning: [8.0, 9.5]
      evening: [17.0, 20.0]  # Tourist traffic extends later
    traffic_density: high
```

### Realistic daily traffic curves

Replace the single `DAILY_TRAFFIC` array with per-fiber curves built from peak hours config. Each fiber gets its own density multiplier function that produces the characteristic double-peak pattern of French urban traffic.

## Phase 2 — Event-driven incidents

### Road events (causes)

Instead of spawning "incident" objects, spawn **road events** that affect vehicle behavior:

| Event | Effect on vehicles | Detection signature |
|-------|-------------------|---------------------|
| **Stopped vehicle** | One vehicle stops (speed→0), others queue behind | Sudden speed drop to 0 at one point, queue forming upstream |
| **Lane closure** | One lane blocked, vehicles merge | Speed drop to ~50% in affected section, flow reduction |
| **Slow vehicle** | One vehicle at 30 km/h in fast lane | Moderate speed drop, vehicles weaving around |
| **Congestion wave** | Density exceeds capacity | Progressive speed drop across section, stop-and-go pattern |
| **Accident** | Two vehicles stop, debris blocks lane(s) | Abrupt speed→0 for multiple vehicles, rapid queue formation |

The Overseer spawns these events based on traffic conditions:
- **Congestion** emerges naturally when density is high (rush hour)
- **Stopped vehicle** / **accident**: random but probability scales with traffic density and speed variance
- **Slow vehicle**: random, more common on fast roads

### Vehicle response to events

Vehicles don't see "incidents" — they see the vehicle ahead of them. Current car-following model already handles this: if a vehicle stops, the one behind brakes, creating a chain reaction. The simulation just needs to:

1. Force a specific vehicle to stop/slow (the "cause")
2. Let physics propagate the effect upstream
3. Let the Overseer detect the resulting speed anomaly

## Phase 3 — Incident detection (Overseer)

The Overseer monitors aggregated metrics and declares incidents when thresholds are crossed. This mirrors what the real AI pipeline does (simplified).

### Detection rules

```python
class IncidentOverseer:
    """Monitors simulation detections and declares incidents."""

    def check(self, section_metrics: dict[str, SectionMetrics]) -> list[NewIncident]:
        incidents = []
        for section_id, metrics in section_metrics.items():
            # Sudden speed drop (accident/stopped vehicle)
            if metrics.speed_drop_pct > 40 and metrics.duration_s >= 10:
                incidents.append(NewIncident(
                    type="accident" if metrics.min_speed < 5 else "slowdown",
                    severity=self._classify_severity(metrics),
                    ...
                ))

            # Congestion (progressive slowdown)
            if metrics.avg_speed < metrics.free_flow_speed * 0.5 and metrics.duration_s >= 30:
                incidents.append(NewIncident(type="congestion", ...))

            # Anomaly (unusual pattern)
            if metrics.speed_variance > threshold:
                incidents.append(NewIncident(type="anomaly", ...))

        return incidents
```

### SectionMetrics (rolling window)

Per-section rolling window (last 30s) tracking:
- `avg_speed` — current average speed
- `free_flow_speed` — baseline for this section/hour (from Phase 1 config)
- `speed_drop_pct` — percentage drop from free-flow
- `min_speed` — minimum observed speed
- `duration_s` — how long the anomaly has persisted
- `speed_variance` — standard deviation of speed
- `flow` — vehicles per minute

### Severity classification

| Metric | Low | Medium | High | Critical |
|--------|-----|--------|------|----------|
| Speed drop | 20-40% | 40-60% | 60-80% | >80% |
| Duration | <1 min | 1-5 min | 5-15 min | >15 min |
| Affected channels | <10 | 10-30 | 30-50 | >50 |
| Speed near zero | No | No | Partial | Full stop |

Severity escalates over time if the situation worsens. A "low" slowdown that persists and deepens gets upgraded to "medium" then "high".

## Phase 4 — Coherent snapshots

Since incidents are now detected from actual vehicle behavior, snapshots are automatically coherent:

1. Vehicles are doing their thing
2. An event occurs (vehicle stops, lane blocked)
3. Upstream vehicles slow down → queue forms
4. Overseer detects the speed drop → declares incident
5. Snapshot captures the ±60s window around detection time
6. The pre-incident half shows normal traffic → sudden change → the post-incident half shows the queue growing or clearing

No artificial speed manipulation needed — the snapshot shows exactly what happened.

## Phase 5 — Polish

- **Incident resolution**: Overseer marks incident resolved when metrics recover (speed returns to >80% of free-flow for >30s)
- **Event lifecycle**: stopped vehicles get "towed" after a random duration (5-30 min sim time), lane closures reopen, slow vehicles exit
- **Rush hour congestion**: at peak density, natural congestion waves emerge from the car-following model without any explicit events
- **Night mode**: minimal traffic, occasional vehicles, very rare incidents
- **Weekend patterns**: different traffic curve (later peaks, more distributed)

## Files to modify

| File | Changes |
|------|---------|
| `apps/realtime/simulation.py` | Major rewrite: add Overseer, event system, per-road config, detection-driven incidents |
| `fibers.yaml` or new `simulation.yaml` | Per-fiber speed/traffic config |
| `apps/realtime/management/commands/run_simulation.py` | Load new config |

## Dependencies

- None — this is a self-contained backend change
- Frontend doesn't need changes (same incident/detection/snapshot data format)
- Snapshot recording (rolling buffer + fixed window) stays the same

## Success criteria

1. An incident snapshot shows a clear speed transition: normal → drop → (recovery or worsening)
2. Incidents only appear when there's a genuine anomaly in the simulated traffic
3. Rush hour naturally produces more incidents than off-peak
4. Each fiber has distinct speed characteristics matching the real road
5. A human watching the simulation can't easily tell it's not real data (at the aggregate level)
