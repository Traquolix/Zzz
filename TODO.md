# SequoIA — Current Sprint

> This file tracks only the active sprint. The backlog lives in
> [GitHub Issues](https://github.com/Traquolix/Sequoia/issues).
> Completed sprints are archived in `TODO/history.md`.

## Sprint 5 — May 2026 (due May 30)

### In Progress

1. [ ] **Codebase hygiene sweep** [#201] — remaining items:
   - [ ] Circular `realtime` ↔ `monitoring` imports (deferred imports hiding coupling)
   - [ ] `shared` imports from domain apps (`shared/signals.py`, `shared/views.py` → inverted deps)
   - [ ] `sync_fibers` dual-write undocumented (PG + ClickHouse, CH failure swallowed)
   - [ ] Dead Zustand mirroring in `RealtimeProvider` (writes to store nothing reads)
   - [ ] Duplicated UI patterns (sticky headers 3×, KPI cards 4×, toggle groups 2×, date formatting 3×)
   - [ ] Unsafe type assertions (`as DataFlow`, double-cast `as unknown as RefObject`, JSON casts)

### Open

2. [ ] **Store vehicle strength/weight for display color** [#187]
3. [ ] **Re-apply gunicorn multi-worker with Redis sync fix** [#133]
4. [ ] **CPAB/GPU memory leaks in AI engine** [#100]

### Sprint 4 — Completed (March 31)

All 17 issues closed. Highlights: data coverage map (#122), fiber PostgreSQL
consolidation (#198), DashboardMap decomposition (#180–#182), OpenTelemetry
migration (#220), flow-aware fiber lines.
