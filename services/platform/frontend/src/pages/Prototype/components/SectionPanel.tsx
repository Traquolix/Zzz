import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { fibers, getSpeedColor } from '../data'
import type { Section } from '../types'
import { Sparkline } from './Sparkline'

interface SectionPanelProps {
    open: boolean
    sections: Section[]
    onSelectSection: (id: string) => void
    onAddSection: () => void
    onDeleteSection: (id: string) => void
    onClose: () => void
}

export function SectionPanel({ open, sections, onSelectSection, onAddSection, onDeleteSection, onClose }: SectionPanelProps) {
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

    return (
        <div
            className={cn(
                'proto-panel absolute top-0 left-0 h-full w-[320px] z-20',
                'bg-[var(--proto-surface)] border-r border-[var(--proto-border)]',
                'flex flex-col',
                open ? 'proto-panel-visible' : 'proto-panel-enter-left',
            )}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--proto-border)]">
                <h2 className="text-sm font-semibold text-[var(--proto-text)]">Sections</h2>
                <div className="flex items-center gap-2">
                    <button
                        onClick={onAddSection}
                        className="text-xs px-2 py-1 rounded bg-[var(--proto-accent)] text-white hover:bg-[var(--proto-accent)]/80 transition-colors cursor-pointer"
                    >
                        + Add
                    </button>
                    <button
                        onClick={onClose}
                        className="text-[var(--proto-text-muted)] hover:text-[var(--proto-text)] transition-colors text-lg leading-none cursor-pointer"
                    >
                        &times;
                    </button>
                </div>
            </div>

            {/* Section list */}
            <div className="flex-1 overflow-y-auto">
                {sections.length === 0 ? (
                    <div className="flex items-center justify-center h-32 text-[var(--proto-text-muted)] text-sm">
                        No sections yet
                    </div>
                ) : (
                    sections.map((section) => {
                        const fiber = fibers.find((f) => f.id === section.fiberId)
                        return (
                            <div
                                key={section.id}
                                className="group relative border-b border-[var(--proto-border)]"
                            >
                                <button
                                    onClick={() => onSelectSection(section.id)}
                                    className={cn(
                                        'w-full text-left px-4 py-3',
                                        'hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer',
                                    )}
                                >
                                    <div className="flex items-center gap-2 mb-1">
                                        <span
                                            className="w-2 h-0.5 rounded-full"
                                            style={{ backgroundColor: fiber?.color }}
                                        />
                                        <span className="text-sm text-[var(--proto-text)] font-medium truncate">
                                            {section.name}
                                        </span>
                                    </div>

                                    <div className="flex items-center justify-between text-xs text-[var(--proto-text-secondary)]">
                                        <div className="flex items-center gap-3">
                                            <span>
                                                <span style={{ color: getSpeedColor(section.avgSpeed) }}>{section.avgSpeed}</span> km/h
                                            </span>
                                            <span>{section.flow} veh/h</span>
                                            <span className="text-[var(--proto-text-muted)]">
                                                Ch {section.startChannel}-{section.endChannel}
                                            </span>
                                        </div>
                                        <Sparkline
                                            data={section.speedHistory}
                                            color={fiber?.color}
                                            width={48}
                                            height={16}
                                        />
                                    </div>
                                </button>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        onDeleteSection(section.id)
                                    }}
                                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-[var(--proto-text-muted)] hover:text-[var(--proto-red)] transition-all text-xs cursor-pointer px-1"
                                >
                                    &times;
                                </button>
                            </div>
                        )
                    })
                )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 text-xs text-[var(--proto-text-muted)] border-t border-[var(--proto-border)]">
                {sections.length} section{sections.length !== 1 ? 's' : ''}
            </div>
        </div>
    )
}
