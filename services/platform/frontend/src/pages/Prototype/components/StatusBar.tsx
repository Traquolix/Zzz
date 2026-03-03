import { cn } from '@/lib/utils'
import { fibers, incidents } from '../data'
import type { Section } from '../types'

const cableCount = new Set(fibers.map((f) => f.parentCableId)).size

interface StatusBarProps {
    sections: Section[]
    onOpenIncidents: () => void
    onOpenSections: () => void
}

export function StatusBar({ sections, onOpenIncidents, onOpenSections }: StatusBarProps) {
    const activeIncidents = incidents.filter((i) => !i.resolved).length
    const criticalCount = incidents.filter((i) => !i.resolved && i.severity === 'critical').length

    return (
        <div className="absolute top-4 left-4 z-10 flex gap-2">
            <button
                onClick={onOpenIncidents}
                className={cn(
                    'flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
                    'bg-[var(--proto-surface)] border border-[var(--proto-border)]',
                    'hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer',
                )}
            >
                <span
                    className={cn(
                        'w-2 h-2 rounded-full',
                        criticalCount > 0 ? 'bg-[var(--proto-red)] animate-pulse' : 'bg-[var(--proto-amber)]',
                    )}
                />
                <span className="text-[var(--proto-text)]">
                    {activeIncidents} incident{activeIncidents !== 1 ? 's' : ''}
                </span>
                {criticalCount > 0 && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                        {criticalCount} critical
                    </span>
                )}
            </button>

            <button
                onClick={onOpenSections}
                className={cn(
                    'flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
                    'bg-[var(--proto-surface)] border border-[var(--proto-border)]',
                    'hover:bg-[var(--proto-surface-raised)] transition-colors cursor-pointer',
                )}
            >
                <span className="text-[var(--proto-text-secondary)]">
                    {cableCount} cables · {sections.length} section{sections.length !== 1 ? 's' : ''}
                </span>
            </button>
        </div>
    )
}
