## Summary

<!-- 1-3 bullet points describing what this PR does and why -->

## Related Issue

<!-- REQUIRED: Link the issue this PR resolves. Use "Closes #N" so GitHub
     auto-closes it on merge. If it doesn't fully resolve the issue,
     use "Relates to #N" instead. Do NOT leave this blank. -->

Closes #

## Services Affected

<!-- List the affected services, e.g.: Pipeline — AI Engine, Platform — Backend -->

## Testing Done

<!-- Describe what you tested and how -->

## Checklist

### Validation
- [ ] `make lint` passes
- [ ] `make typecheck` passes
- [ ] `make test` passes (if tests exist for affected code)

### Hard Rules
- [ ] No new secrets or credentials in code
- [ ] No integration tests modified
- [ ] Dependencies updated in lock/requirements files (if applicable)
- [ ] `ARCHITECTURE.md` updated (if data flow changed)

### Consistency
- [ ] No unrelated changes bundled (one concern per PR)
- [ ] REST endpoints touching sim + live data are flow-aware (`?flow=` param or equivalent)
- [ ] ClickHouse error handling uses `@clickhouse_fallback` where applicable (not manual try/except)
- [ ] Broadcasts use shared helpers (`broadcast_per_org`, `broadcast_to_orgs`, `broadcast_shm`), not inline `group_send`
- [ ] All user-visible strings in both `en.json` and `fr.json`
