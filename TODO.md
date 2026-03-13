# SequoIA — Current Sprint

> This file tracks only the active sprint. The backlog lives in
> [GitHub Issues](https://github.com/Traquolix/Sequoia/issues).
> Completed sprints are archived in `TODO/history.md`.

## Sprint 3 — March 2026 (due March 31)

### Bugs

1. [x] **SHM cache warm-up blocks Docker build** [#113] — PR #115
2. [x] **Section queries ignore direction in live mode** [#112]
3. [x] **Spectral heatmap axis labels unreadable** [#74]
4. [x] **SHM query keys should include infrastructureId** [#101]
5. [x] **Mapbox fiber-lines zoom expression error on hover** [#104] — already fixed
6. [x] **Detections staggered in live mode** [#102] — no longer reproducible
7. [x] **Clean up toasts when switching sim↔live** [#130] — PR #134

### Features

8. [ ] **Clicking incident toast → navigate + mark read** [#36]
9. [ ] **Clear all / read all notifications** [#120]
10. [ ] **Hover on beta: pipeline health info** [#128]
11. [ ] **API to get access to detection data** [#132]
12. [ ] **Only display map locations with data** [#122]
13. [ ] **Auto-reconnect UX for live flow** [#103]
14. [ ] **Show version on BETA tag hover** [#30]

### Backlog (deferred from Sprint 3)

- **Gunicorn multi-worker** [#133] — reverted, needs Redis sync fix
- **CPAB/GPU memory leaks** [#100] — pipeline AI engine, heavy
- **Fix pipeline mypy errors** [#60] — 141 errors, ongoing
- **Real-time SHM end-to-end** [#11] — multi-sprint feature
- **Differentiate VL / PL** — no issue yet, car/truck classification
- **Add new infrastructures to populate SHM list** — no issue yet
