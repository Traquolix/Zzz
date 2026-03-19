import { useState } from 'react'
import { cn } from '@/lib/utils'
import { severityColor } from '../data'
import { useIncidentSnapshot } from '@/hooks/useIncidentSnapshot'
import type { ProtoIncident, ProtoAction, Severity, Section } from '../types'
import { useRealtime } from '@/hooks/useRealtime'
import { TimeSeriesChart } from './TimeSeriesChart'

// ── Incident list ───────────────────────────────────────────────────────

export function IncidentList({
  incidents,
  filterSeverity,
  hideResolved,
  sortBy,
  dispatch,
  onHighlightIncident,
  onClearHighlight,
  unseenIds,
  onMarkSeen,
}: {
  incidents: ProtoIncident[]
  filterSeverity: Severity | null
  hideResolved: boolean
  sortBy: 'newest' | 'oldest'
  dispatch: React.Dispatch<ProtoAction>
  onHighlightIncident?: (id: string) => void
  onClearHighlight?: () => void
  unseenIds?: Set<string>
  onMarkSeen?: (id: string) => void
}) {
  let filtered = filterSeverity ? incidents.filter(i => i.severity === filterSeverity) : incidents
  if (hideResolved) filtered = filtered.filter(i => !i.resolved)

  const sorted = [...filtered].sort((a, b) => {
    const ta = new Date(a.detectedAt).getTime()
    const tb = new Date(b.detectedAt).getTime()
    return sortBy === 'newest' ? tb - ta : ta - tb
  })

  return (
    <>
      {sorted.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-cq-sm">
          No incidents match this filter
        </div>
      ) : (
        <div className="flex flex-col px-3 py-1">
          {sorted.map(inc => (
            <button
              key={inc.id}
              onClick={() => dispatch({ type: 'SELECT_INCIDENT', id: inc.id })}
              onMouseEnter={() => {
                onHighlightIncident?.(inc.id)
                onMarkSeen?.(inc.id)
              }}
              onMouseLeave={() => onClearHighlight?.()}
              className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <span
                  className="shrink-0 w-2 h-2 rounded-full mt-1.5"
                  style={{ backgroundColor: severityColor[inc.severity] }}
                />
                {unseenIds?.has(inc.id) && (
                  <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[var(--proto-accent)] mt-2 -ml-1.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-cq-sm text-[var(--proto-text)] font-medium truncate">{inc.title}</span>
                    <span className="shrink-0 text-cq-xs tabular-nums text-[var(--proto-text-secondary)]">
                      {new Date(inc.detectedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-cq-xxs text-[var(--proto-text-muted)] mt-0.5">
                    <span>
                      Ch {inc.channel}
                      {inc.channelEnd && inc.channelEnd !== inc.channel ? `–${inc.channelEnd}` : ''}
                    </span>
                    <span className="opacity-40">·</span>
                    <span>{new Date(inc.detectedAt).toLocaleDateString([], { day: 'numeric', month: 'short' })}</span>
                    {inc.resolved && (
                      <>
                        <span className="opacity-40">·</span>
                        <span className="text-[var(--proto-green)]">resolved</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </>
  )
}

// ── Incident detail ─────────────────────────────────────────────────────

export function IncidentDetail({
  incident,
  sections,
  dispatch,
  onBack,
}: {
  incident: ProtoIncident
  sections: Section[]
  dispatch: React.Dispatch<ProtoAction>
  onBack: () => void
}) {
  const { flow } = useRealtime()

  // Find containing section by channel range
  const relatedSection = sections.find(
    s =>
      s.fiberId === incident.fiberId &&
      s.direction === incident.direction &&
      incident.channel >= s.startChannel &&
      incident.channel <= s.endChannel,
  )

  // Fetch snapshot data from API — polls every 1s until snapshot is complete
  const {
    points: snapshotData,
    loading: snapshotLoading,
    complete: snapshotComplete,
  } = useIncidentSnapshot(incident.id, flow)

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(incident.description)

  return (
    <div className="proto-analysis-enter flex flex-col">
      <div className="sticky top-0 z-10 bg-[var(--proto-surface)] border-b border-[var(--proto-border)] px-4 py-3 flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-cq-sm cursor-pointer"
        >
          &larr; Back
        </button>
        <span className="text-cq-sm font-semibold text-[var(--proto-text)] truncate">{incident.title}</span>
        <span
          className="text-cq-2xs font-medium px-1.5 py-0.5 rounded capitalize shrink-0"
          style={{ backgroundColor: `${severityColor[incident.severity]}20`, color: severityColor[incident.severity] }}
        >
          {incident.severity}
        </span>
      </div>

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* Speed metrics when available */}
        {(incident.speedBefore != null || incident.speedDuring != null) && (
          <div className="grid grid-cols-3 gap-2 pb-3 border-b border-[var(--proto-border)]">
            {incident.speedBefore != null && (
              <div className="rounded-lg border border-[var(--proto-border)] p-2.5">
                <div className="text-cq-2xs text-[var(--proto-text-muted)] uppercase tracking-wider mb-0.5">Before</div>
                <span className="text-cq-lg font-semibold text-[var(--proto-text)]">
                  {Math.round(incident.speedBefore)}
                </span>
                <span className="text-cq-2xs text-[var(--proto-text-muted)] ml-0.5">km/h</span>
              </div>
            )}
            {incident.speedDuring != null && (
              <div className="rounded-lg border border-[var(--proto-border)] p-2.5">
                <div className="text-cq-2xs text-[var(--proto-text-muted)] uppercase tracking-wider mb-0.5">During</div>
                <span className="text-cq-lg font-semibold text-[var(--proto-red)]">
                  {Math.round(incident.speedDuring)}
                </span>
                <span className="text-cq-2xs text-[var(--proto-text-muted)] ml-0.5">km/h</span>
              </div>
            )}
            {incident.speedDropPercent != null && (
              <div className="rounded-lg border border-[var(--proto-border)] p-2.5">
                <div className="text-cq-2xs text-[var(--proto-text-muted)] uppercase tracking-wider mb-0.5">Drop</div>
                <span className="text-cq-lg font-semibold text-[var(--proto-red)]">
                  {Math.round(incident.speedDropPercent)}
                </span>
                <span className="text-cq-2xs text-[var(--proto-text-muted)] ml-0.5">%</span>
              </div>
            )}
          </div>
        )}

        <div className="pb-3 border-b border-[var(--proto-border)]">
          {editing ? (
            <div className="flex flex-col gap-2">
              <textarea
                autoFocus
                value={draft}
                onChange={e => setDraft(e.target.value)}
                rows={3}
                className="w-full px-2 py-1.5 rounded bg-[var(--proto-surface)] border border-[var(--proto-border)] text-cq-sm text-[var(--proto-text)] outline-none focus:border-[var(--proto-accent)] resize-none"
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => {
                    setDraft(incident.description)
                    setEditing(false)
                  }}
                  className="px-2 py-1 rounded text-cq-xs text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    dispatch({ type: 'UPDATE_INCIDENT_DESCRIPTION', id: incident.id, description: draft })
                    setEditing(false)
                  }}
                  className="px-2 py-1 rounded text-cq-xs bg-[var(--proto-accent)] text-white cursor-pointer hover:opacity-80 transition-opacity"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div
              className="text-cq-sm text-[var(--proto-text)] mb-2 cursor-pointer hover:bg-[var(--proto-surface-raised)] rounded px-1 -mx-1 py-0.5 transition-colors"
              onClick={() => {
                setDraft(incident.description)
                setEditing(true)
              }}
              title="Click to edit"
            >
              {incident.description}
            </div>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-cq-xs text-[var(--proto-text-secondary)]">
            <span>
              Type: <span className="capitalize">{incident.type}</span>
            </span>
            <span>
              Time: {new Date(incident.detectedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            <span>
              Location: {incident.location[1].toFixed(4)}N, {incident.location[0].toFixed(4)}E
            </span>
            <span>
              Channel: {incident.channel}
              {incident.channelEnd != null && incident.channelEnd !== incident.channel ? `–${incident.channelEnd}` : ''}
            </span>
            <span>
              Status:{' '}
              <span className={cn(incident.resolved ? 'text-[var(--proto-green)]' : 'text-[var(--proto-red)]')}>
                {incident.resolved ? 'Resolved' : 'Active'}
              </span>
            </span>
          </div>
        </div>

        {relatedSection && (
          <div className="pb-3 border-b border-[var(--proto-border)]">
            <h3 className="text-cq-xs font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-2">
              Affected Section
            </h3>
            <div className="text-cq-sm text-[var(--proto-text)] mb-1">{relatedSection.name}</div>
            <div className="flex gap-4 text-cq-xs text-[var(--proto-text-secondary)]">
              <span>{relatedSection.avgSpeed} km/h</span>
              <span>{relatedSection.flow} veh/h</span>
              <span>{relatedSection.occupancy}% occ.</span>
              <span>
                Ch {relatedSection.startChannel}-{relatedSection.endChannel}
              </span>
            </div>
          </div>
        )}

        <div>
          <h3 className="text-cq-xs font-medium text-[var(--proto-text-muted)] uppercase tracking-wider mb-3">
            Snapshot
            {!snapshotComplete && !snapshotLoading && (
              <span className="ml-2 text-[var(--proto-accent)] animate-pulse">collecting...</span>
            )}
          </h3>
          {snapshotLoading ? (
            <div className="h-[200px] rounded bg-[var(--proto-surface)] animate-pulse flex items-center justify-center">
              <span className="text-cq-xs text-[var(--proto-text-muted)]">Loading snapshot...</span>
            </div>
          ) : snapshotData ? (
            <TimeSeriesChart
              data={snapshotData}
              incidentTime={new Date(incident.detectedAt).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
              })}
            />
          ) : (
            <div className="text-cq-xs text-[var(--proto-text-muted)] italic py-4 text-center">
              No snapshot data available
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
