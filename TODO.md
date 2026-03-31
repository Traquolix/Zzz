# SequoIA — Current Sprint

> This file tracks only the active sprint. The backlog lives in
> [GitHub Issues](https://github.com/Traquolix/Sequoia/issues).
> Completed sprints are archived in `TODO/history.md`.

## Sprint 5 — May 2026 (due May 30)

### Done

1. [x] **Codebase hygiene sweep** [#201] — all items resolved:
   - [x] Circular `realtime` ↔ `monitoring` imports → moved to `apps.shared` (#250)
   - [x] `shared` inversions → distributed audit signals, cache-based health (#250)
   - [x] `sync_fibers` dual-write → documented (#249)
   - [x] Dead Zustand mirroring → removed store + dependency (#249)
   - [x] Date formatting → consolidated in `formatters.ts` (#249)
   - [x] Unsafe type assertions → runtime guards + typed constants (#249)
   - [x] Duplicated UI patterns → shared `ToggleGroup`, `MetricCard` reuse (#251)

### Open

2. [ ] **Store vehicle strength/weight for display color** [#187]
3. [ ] **Re-apply gunicorn multi-worker with Redis sync fix** [#133]
4. [ ] **CPAB/GPU memory leaks in AI engine** [#100]

### Sprint 4 — Completed (March 31)

All 17 issues closed. Highlights: data coverage map (#122), fiber PostgreSQL
consolidation (#198), DashboardMap decomposition (#180–#182), OpenTelemetry
migration (#220), flow-aware fiber lines.
