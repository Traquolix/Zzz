import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { incidents, severityColor } from '../data'
import type { Severity } from '../types'

interface IncidentPanelProps {
    open: boolean
    filterSeverity: Severity | null
    onFilterChange: (severity: Severity | null) => void
    onSelectIncident: (id: string) => void
    onClose: () => void
}

const severityOrder: Severity[] = ['critical', 'high', 'medium', 'low']

export function IncidentPanel({
    open,
    filterSeverity,
    onFilterChange,
    onSelectIncident,
    onClose,
}: IncidentPanelProps) {
    const [shouldRender, setShouldRender] = useState(open)

    useEffect(() => {
        if (open) {
            setShouldRender(true)
        } else {
            const timer = setTimeout(() => setShouldRender(false), 250)
            return () => clearTimeout(timer)
        }
    }, [open])

    if (!shouldRender) return null

    const filtered = filterSeverity
        ? incidents.filter((i) => i.severity === filterSeverity)
        : incidents

    const sorted = [...filtered].sort((a, b) => {
        return severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity)
    })

    return (
        <div
            className={cn(
                'proto-panel absolute top-0 right-0 h-full w-[350px] z-20',
                'bg-[var(--proto-surface)] border-l border-[var(--proto-border)]',
                'flex flex-col',
                open ? 'proto-panel-visible' : 'proto-panel-enter-right',
            )}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--proto-border)]">
                <h2 className="text-sm font-semibold text-[var(--proto-text)]">Incidents</h2>
                <button
                    onClick={onClose}
                    className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-lg leading-none cursor-pointer"
                >
                    &times;
                </button>
            </div>

            {/* Severity filters */}
            <div className="flex gap-1.5 px-4 py-2 border-b border-[var(--proto-border)]">
                <FilterChip
                    label="All"
                    active={filterSeverity === null}
                    onClick={() => onFilterChange(null)}
                />
                {severityOrder.map((s) => (
                    <FilterChip
                        key={s}
                        label={s}
                        color={severityColor[s]}
                        active={filterSeverity === s}
                        onClick={() => onFilterChange(s)}
                    />
                ))}
            </div>

            {/* Incident list */}
            <div className="flex-1 overflow-y-auto">
                {sorted.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-sm">
                        No incidents match this filter
                    </div>
                ) : (
                    sorted.map((inc) => (
                        <button
                            key={inc.id}
                            onClick={() => onSelectIncident(inc.id)}
                            className={cn(
                                'w-full text-left px-4 py-3 border-b border-[var(--proto-border)]',
                                'hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer',
                            )}
                        >
                            <div className="flex items-start gap-2">
                                <span
                                    className="w-2 h-2 rounded-full mt-1.5 shrink-0"
                                    style={{ backgroundColor: severityColor[inc.severity] }}
                                />
                                <div className="min-w-0">
                                    <div className="text-sm text-[var(--proto-text)] font-medium truncate">
                                        {inc.title}
                                    </div>
                                    <div className="text-xs text-[var(--proto-text-muted)] mt-0.5">
                                        {inc.type} · {new Date(inc.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        {inc.resolved && (
                                            <span className="ml-1.5 text-[var(--proto-green)]">resolved</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </button>
                    ))
                )}
            </div>

            {/* Footer count */}
            <div className="px-4 py-2 text-xs text-[var(--proto-text-muted)] border-t border-[var(--proto-border)]">
                {sorted.length} incident{sorted.length !== 1 ? 's' : ''}
            </div>
        </div>
    )
}

function FilterChip({
    label,
    color,
    active,
    onClick,
}: {
    label: string
    color?: string
    active: boolean
    onClick: () => void
}) {
    return (
        <button
            onClick={onClick}
            className={cn(
                'px-2 py-0.5 rounded text-xs capitalize transition-colors cursor-pointer',
                active
                    ? 'bg-[var(--proto-accent)] text-white'
                    : 'bg-[var(--proto-surface-raised)] text-[var(--proto-text-secondary)] hover:text-[var(--proto-text)]',
            )}
        >
            {color && (
                <span
                    className="inline-block w-1.5 h-1.5 rounded-full mr-1"
                    style={{ backgroundColor: color }}
                />
            )}
            {label}
        </button>
    )
}
