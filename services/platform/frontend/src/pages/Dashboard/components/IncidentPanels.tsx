import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { severityColor } from '@/lib/theme'
import { useIncidentSnapshot } from '@/hooks/useIncidentSnapshot'
import type { DisplayIncident, MapPageAction, Severity, Section } from '../types'
import { useRealtime } from '@/hooks/useRealtime'
import { TimeSeriesChart } from './TimeSeriesChart'
import { PanelEmptyState } from './PanelEmptyState'
import { DetailHeader } from './DetailHeader'
import { MetricCard } from './MetricCard'

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
  incidents: DisplayIncident[]
  filterSeverity: Severity | null
  hideResolved: boolean
  sortBy: 'newest' | 'oldest'
  dispatch: React.Dispatch<MapPageAction>
  onHighlightIncident?: (id: string) => void
  onClearHighlight?: () => void
  unseenIds?: Set<string>
  onMarkSeen?: (id: string) => void
}) {
  const { t } = useTranslation()
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
        <PanelEmptyState message={t('incidents.noMatchingFilter')} />
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
              className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[var(--dash-surface-raised)] transition-colors cursor-pointer"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <span
                  className="shrink-0 w-2 h-2 rounded-full mt-1.5"
                  style={{ backgroundColor: severityColor[inc.severity] }}
                />
                {unseenIds?.has(inc.id) && (
                  <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[var(--dash-accent)] mt-2 -ml-1.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-cq-sm text-[var(--dash-text)] font-medium truncate">{inc.title}</span>
                    <span className="shrink-0 text-cq-xs tabular-nums text-[var(--dash-text-secondary)]">
                      {new Date(inc.detectedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-cq-xxs text-[var(--dash-text-muted)] mt-0.5">
                    <span>
                      Ch {inc.channel}
                      {inc.channelEnd && inc.channelEnd !== inc.channel ? `–${inc.channelEnd}` : ''}
                    </span>
                    <span className="opacity-40">·</span>
                    <span>{new Date(inc.detectedAt).toLocaleDateString([], { day: 'numeric', month: 'short' })}</span>
                    {inc.resolved && (
                      <>
                        <span className="opacity-40">·</span>
                        <span className="text-[var(--dash-green)]">{t('incidents.resolved').toLowerCase()}</span>
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
  incident: DisplayIncident
  sections: Section[]
  dispatch: React.Dispatch<MapPageAction>
  onBack: () => void
}) {
  const { t } = useTranslation()
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
    <div className="dash-analysis-enter flex flex-col">
      <DetailHeader
        title={incident.title}
        onBack={onBack}
        badge={
          <span
            className="text-cq-2xs font-medium px-1.5 py-0.5 rounded capitalize shrink-0"
            style={{
              backgroundColor: `${severityColor[incident.severity]}20`,
              color: severityColor[incident.severity],
            }}
          >
            {incident.severity}
          </span>
        }
      />

      <div className="px-4 py-4 flex flex-col gap-3">
        {/* Speed metrics when available */}
        {(incident.speedBefore != null || incident.speedDuring != null) && (
          <div className="grid grid-cols-3 gap-2 pb-3 border-b border-[var(--dash-border)]">
            {incident.speedBefore != null && (
              <MetricCard
                compact
                label={t('incidents.detail.before')}
                value={Math.round(incident.speedBefore)}
                unit="km/h"
              />
            )}
            {incident.speedDuring != null && (
              <MetricCard
                compact
                label={t('incidents.detail.during')}
                value={Math.round(incident.speedDuring)}
                unit="km/h"
                valueColor="var(--dash-red)"
              />
            )}
            {incident.speedDropPercent != null && (
              <MetricCard
                compact
                label={t('incidents.detail.drop')}
                value={Math.round(incident.speedDropPercent)}
                unit="%"
                valueColor="var(--dash-red)"
              />
            )}
          </div>
        )}

        <div className="pb-3 border-b border-[var(--dash-border)]">
          {editing ? (
            <div className="flex flex-col gap-2">
              <textarea
                autoFocus
                value={draft}
                onChange={e => setDraft(e.target.value)}
                rows={3}
                className="w-full px-2 py-1.5 rounded bg-[var(--dash-surface)] border border-[var(--dash-border)] text-cq-sm text-[var(--dash-text)] outline-none focus:border-[var(--dash-accent)] resize-none"
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => {
                    setDraft(incident.description)
                    setEditing(false)
                  }}
                  className="px-2 py-1 rounded text-cq-xs text-[var(--dash-text-muted)] hover:text-[var(--dash-text)] transition-colors cursor-pointer"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={() => {
                    dispatch({ type: 'UPDATE_INCIDENT_DESCRIPTION', id: incident.id, description: draft })
                    setEditing(false)
                  }}
                  className="px-2 py-1 rounded text-cq-xs bg-[var(--dash-accent)] text-white cursor-pointer hover:opacity-80 transition-opacity"
                >
                  {t('common.save')}
                </button>
              </div>
            </div>
          ) : (
            <div
              role="button"
              tabIndex={0}
              className="text-cq-sm text-[var(--dash-text)] mb-2 cursor-pointer hover:bg-[var(--dash-surface-raised)] rounded px-1 -mx-1 py-0.5 transition-colors"
              onClick={() => {
                setDraft(incident.description)
                setEditing(true)
              }}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setDraft(incident.description)
                  setEditing(true)
                }
              }}
              title={t('common.clickToEdit')}
            >
              {incident.description}
            </div>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-cq-xs text-[var(--dash-text-secondary)]">
            <span>
              {t('incidents.detail.type')} <span className="capitalize">{incident.type}</span>
            </span>
            <span>
              {t('incidents.detail.time')}{' '}
              {new Date(incident.detectedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            <span>
              {t('incidents.detail.location')} {incident.location[1].toFixed(4)}N, {incident.location[0].toFixed(4)}E
            </span>
            <span>
              {t('incidents.detail.channel')} {incident.channel}
              {incident.channelEnd != null && incident.channelEnd !== incident.channel ? `–${incident.channelEnd}` : ''}
            </span>
            <span>
              {t('incidents.detail.status')}{' '}
              <span className={cn(incident.resolved ? 'text-[var(--dash-green)]' : 'text-[var(--dash-red)]')}>
                {incident.resolved ? t('incidents.resolved') : t('incidents.ongoing')}
              </span>
            </span>
          </div>
        </div>

        {relatedSection && (
          <div className="pb-3 border-b border-[var(--dash-border)]">
            <h3 className="text-cq-xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider mb-2">
              {t('incidents.detail.affectedSection')}
            </h3>
            <div className="text-cq-sm text-[var(--dash-text)] mb-1">{relatedSection.name}</div>
            <div className="flex gap-4 text-cq-xs text-[var(--dash-text-secondary)]">
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
          <h3 className="text-cq-xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider mb-3">
            {t('incidents.detail.snapshot')}
            {!snapshotComplete && !snapshotLoading && (
              <span className="ml-2 text-[var(--dash-accent)] animate-pulse">{t('incidents.detail.collecting')}</span>
            )}
          </h3>
          {snapshotLoading ? (
            <div className="h-[200px] rounded bg-[var(--dash-surface)] animate-pulse flex items-center justify-center">
              <span className="text-cq-xs text-[var(--dash-text-muted)]">{t('incidents.loadingSnapshot')}</span>
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
            <div className="text-cq-xs text-[var(--dash-text-muted)] italic py-4 text-center">
              {t('common.noSnapshot')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
