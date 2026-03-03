import { fibers } from '../data'

const cables = [...new Map(fibers.map((f) => [f.parentCableId, f])).values()]

const speedLegend = [
    { label: '> 80 km/h', color: '#22c55e' },
    { label: '60-80', color: '#eab308' },
    { label: '30-60', color: '#f97316' },
    { label: '< 30', color: '#ef4444' },
]

export function Legend() {
    return (
        <div
            className="absolute bottom-4 right-4 z-10 px-3 py-2.5 rounded-lg text-xs
                        bg-[var(--proto-surface)]/90 border border-[var(--proto-border)]
                        backdrop-blur-sm"
        >
            <div className="text-[var(--proto-text-muted)] mb-1.5 font-medium uppercase tracking-wider text-[10px]">
                Cables
            </div>
            <div className="flex flex-col gap-1">
                {cables.map((f) => (
                    <div key={f.parentCableId} className="flex items-center gap-2">
                        <span
                            className="w-3 h-0.5 rounded-full inline-block"
                            style={{ backgroundColor: f.color }}
                        />
                        <span className="text-[var(--proto-text-secondary)]">{f.name}</span>
                    </div>
                ))}
            </div>

            <div className="mt-2 pt-2 border-t border-[var(--proto-border)]">
                <div className="text-[var(--proto-text-muted)] mb-1 font-medium uppercase tracking-wider text-[10px]">
                    Vehicle Speed
                </div>
                <div className="flex gap-3">
                    {speedLegend.map((s) => (
                        <div key={s.label} className="flex items-center gap-1">
                            <span
                                className="w-1.5 h-1.5 rounded-full"
                                style={{ backgroundColor: s.color }}
                            />
                            <span className="text-[var(--proto-text-muted)]">{s.label}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
