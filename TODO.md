# SequoIA — Current Sprint

> This file tracks only the active sprint. The backlog lives in
> [GitHub Issues](https://github.com/Traquolix/Sequoia/issues).
> Completed sprints are archived in `TODO/history.md`.

## Sprint 5 — Production reliability + quick wins (due May 30)

### Priority 1 — Production reliability

1. [ ] **Re-apply gunicorn multi-worker with Redis sync fix** [#133]
       Single-process uvicorn is the main production bottleneck.
2. [ ] **CPAB/GPU memory leaks in AI engine** [#100]
       Actively leaking memory in deployed AI engine.

### Priority 2 — Contained feature

3. [ ] **Store vehicle strength/weight for display color** [#187]

### Done

4. [x] **Codebase hygiene sweep** [#201] — all items resolved (#249, #250, #251)

## Sprint 6 — Foundations + features (due June 29)

### Foundation (unblocks #99, #222)

5. [ ] **Channel-to-road mapping and bad coupling handling** [#12]
6. [ ] **Add direction awareness to reports, exports, alerting** [#63]

### God-file decomposition (from sweep 2026-03-31)

7. [ ] **Decompose detection_api.py** (1,191 lines → per-resource modules) [#252]
8. [ ] **Extract ModelRegistry from ai_engine/main.py** (968 lines) [#253]
9. [ ] **Split kafka_bridge.py** (519 lines → per-stream modules) [#254]

### Features

10. [ ] **Incident browsing and navigation** [#31]
11. [ ] **Incident replay player** [#9]
12. [ ] **Consolidate frontend to shadcn/ui** [#153]
13. [ ] **Rewrite tests** (unit, integration, component) [#8]
14. [ ] **Display fiber coordinates along directional roads** [#99]

## Backlog (unscheduled)

- [ ] Display kilometric points along roads [#222] (blocked by #12)
- [ ] Real-time SHM data pipeline [#11]
- [ ] Per-user channel permissions [#47]
- [ ] Dev / Preprod / Prod environment isolation [#6]
- [ ] Standardized dev environment [#7]
