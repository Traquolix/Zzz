import { useState, useEffect, type ReactNode } from 'react'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { useTechStats } from '@/hooks/useTechStats'
import { formatDurationMs } from '@/lib/formatters'
import { Wifi, WifiOff, Clock, Car, AlertTriangle, Activity, User } from 'lucide-react'

type Props = {
    children: ReactNode
}

function StatRow({ icon: Icon, label, value, className = '' }: {
    icon: typeof Wifi
    label: string
    value: ReactNode
    className?: string
}) {
    return (
        <div className={`flex items-center justify-between py-1 ${className}`}>
            <div className="flex items-center gap-2 text-slate-500">
                <Icon className="h-3.5 w-3.5" />
                <span className="text-xs">{label}</span>
            </div>
            <div className="text-xs font-medium text-slate-700">{value}</div>
        </div>
    )
}

export function TechStatsHoverCard({ children }: Props) {
    const stats = useTechStats()
    const [shiftHeld, setShiftHeld] = useState(false)
    const [sessionDuration, setSessionDuration] = useState(0)

    // Track shift key
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Shift') setShiftHeld(true)
        }
        const handleKeyUp = (e: KeyboardEvent) => {
            if (e.key === 'Shift') setShiftHeld(false)
        }

        window.addEventListener('keydown', handleKeyDown)
        window.addEventListener('keyup', handleKeyUp)
        return () => {
            window.removeEventListener('keydown', handleKeyDown)
            window.removeEventListener('keyup', handleKeyUp)
        }
    }, [])

    // Update session duration
    useEffect(() => {
        const interval = setInterval(() => {
            setSessionDuration(Date.now() - stats.sessionStart)
        }, 1000)
        return () => clearInterval(interval)
    }, [stats.sessionStart])

    return (
        <HoverCard openDelay={200} closeDelay={100}>
            <HoverCardTrigger asChild>
                {children}
            </HoverCardTrigger>
            <HoverCardContent
                align="start"
                className={`transition-all duration-200 ${shiftHeld ? 'w-80' : 'w-64'}`}
            >
                <div className="space-y-3">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b pb-2">
                        <span className="text-xs font-semibold text-slate-900">System Status</span>
                        <div className={`flex items-center gap-1.5 text-xs ${stats.connected ? 'text-green-600' : 'text-red-500'}`}>
                            {stats.connected ? (
                                <>
                                    <Wifi className="h-3 w-3" />
                                    <span>Connected</span>
                                </>
                            ) : (
                                <>
                                    <WifiOff className="h-3 w-3" />
                                    <span>Disconnected</span>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Basic Stats */}
                    <div className="space-y-0.5">
                        {stats.vehicleCount != null && (
                            <StatRow
                                icon={Car}
                                label="Total Vehicles"
                                value={stats.vehicleCount.toLocaleString()}
                            />
                        )}
                        {stats.activeIncidents != null && (
                            <StatRow
                                icon={AlertTriangle}
                                label="Active Incidents"
                                value={stats.activeIncidents}
                            />
                        )}
                    </div>

                    {/* Expanded Stats (when shift is held) */}
                    {shiftHeld && (
                        <div className="border-t pt-2 space-y-0.5">
                            <StatRow
                                icon={User}
                                label="User"
                                value={stats.username || 'Unknown'}
                            />
                            <StatRow
                                icon={Clock}
                                label="Session"
                                value={formatDurationMs(sessionDuration)}
                            />
                            <StatRow
                                icon={Activity}
                                label="Total Detections"
                                value={stats.totalDetections.toLocaleString()}
                            />
                        </div>
                    )}

                    {/* Footer hint */}
                    {!shiftHeld && (
                        <div className="text-[10px] text-slate-400 text-center pt-1">
                            Hold Shift for more details
                        </div>
                    )}
                </div>
            </HoverCardContent>
        </HoverCard>
    )
}
