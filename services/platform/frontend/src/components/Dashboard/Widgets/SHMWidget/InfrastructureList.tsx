import type { Infrastructure, FrequencyReading } from '@/types/infrastructure'

type Props = {
    infrastructures: Infrastructure[]
    latestReadings: Map<string, FrequencyReading>
    selectedId: string | null
    onSelect: (infra: Infrastructure) => void
    onFlyTo: (infra: Infrastructure, e: React.MouseEvent) => void
}

const TYPE_COLORS: Record<string, { bg: string; text: string }> = {
    bridge: { bg: 'bg-amber-100', text: 'text-amber-700' },
    tunnel: { bg: 'bg-indigo-100', text: 'text-indigo-700' }
}

function BridgeIcon() {
    return (
        <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21" />
        </svg>
    )
}

function TunnelIcon() {
    return (
        <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
        </svg>
    )
}

function LocationIcon() {
    return (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
        </svg>
    )
}

export function InfrastructureList({ infrastructures, latestReadings, selectedId, onSelect, onFlyTo }: Props) {
    return (
        <div className="flex-shrink-0 max-h-[180px] overflow-y-auto border-b border-slate-100">
            {infrastructures.map(infra => {
                const isSelected = infra.id === selectedId
                const reading = latestReadings.get(infra.id)
                const colors = TYPE_COLORS[infra.type] || { bg: 'bg-slate-100', text: 'text-slate-700' }

                return (
                    <div
                        key={infra.id}
                        onClick={() => onSelect(infra)}
                        className={`
                            px-4 py-2.5 cursor-pointer transition-colors border-l-2
                            ${isSelected
                                ? 'bg-amber-50 border-l-amber-500'
                                : 'border-l-transparent hover:bg-slate-50'
                            }
                        `}
                    >
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 min-w-0">
                                {infra.type === 'bridge' ? <BridgeIcon /> : <TunnelIcon />}
                                <div className="min-w-0">
                                    <div className="text-sm font-medium text-slate-700 truncate">
                                        {infra.name}
                                    </div>
                                    <div className="flex items-center gap-2 text-xs text-slate-400">
                                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${colors.bg} ${colors.text}`}>
                                            {infra.type}
                                        </span>
                                        <span>Ch {infra.startChannel}-{infra.endChannel}</span>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                {reading && (
                                    <div className="text-right">
                                        <div className="text-sm font-mono font-medium text-slate-700">
                                            {reading.frequency.toFixed(1)} Hz
                                        </div>
                                        <div className="text-[10px] text-slate-400">
                                            Amp: {(reading.amplitude * 100).toFixed(0)}%
                                        </div>
                                    </div>
                                )}

                                <button
                                    onClick={(e) => onFlyTo(infra, e)}
                                    className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors"
                                    title="Fly to location"
                                >
                                    <LocationIcon />
                                </button>
                            </div>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}
