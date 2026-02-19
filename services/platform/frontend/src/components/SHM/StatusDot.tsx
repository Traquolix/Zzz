import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'

type Status = 'nominal' | 'warning' | 'critical'

type Props = {
    status?: Status
    size?: 'sm' | 'md'
    className?: string
}

const STATUS_CONFIG: Record<Status, { color: string; bgColor: string; label: string }> = {
    nominal: { color: 'bg-emerald-500', bgColor: 'bg-emerald-50', label: 'Nominal' },
    warning: { color: 'bg-amber-500', bgColor: 'bg-amber-50', label: 'Warning' },
    critical: { color: 'bg-red-500', bgColor: 'bg-red-50', label: 'Critical' },
}

export function StatusDot({ status = 'nominal', size = 'md', className = '' }: Props) {
    const [showTooltip, setShowTooltip] = useState(false)
    const [tooltipStyle, setTooltipStyle] = useState<{ top?: number; bottom?: number; left: number; showAbove: boolean }>({ left: 0, showAbove: true })
    const dotRef = useRef<HTMLDivElement>(null)
    const { t } = useTranslation()

    const config = STATUS_CONFIG[status]
    const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5'
    const tooltipWidth = 224 // w-56 = 14rem = 224px
    const tooltipHeight = 160 // approximate height

    const handleMouseEnter = () => {
        if (dotRef.current) {
            const rect = dotRef.current.getBoundingClientRect()
            const showAbove = rect.top > tooltipHeight + 20

            // Center tooltip horizontally on the dot
            let left = rect.left + rect.width / 2 - tooltipWidth / 2
            // Keep tooltip within viewport
            left = Math.max(8, Math.min(left, window.innerWidth - tooltipWidth - 8))

            if (showAbove) {
                setTooltipStyle({ bottom: window.innerHeight - rect.top + 8, left, showAbove: true })
            } else {
                setTooltipStyle({ top: rect.bottom + 8, left, showAbove: false })
            }
        }
        setShowTooltip(true)
    }

    return (
        <div
            ref={dotRef}
            className={`relative inline-flex items-center justify-center ${className}`}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={() => setShowTooltip(false)}
        >
            {/* The dot */}
            <div className={`${dotSize} rounded-full ${config.color} cursor-help`} />

            {/* Tooltip */}
            {showTooltip && (
                <div
                    className="fixed z-[9999] w-56 p-3 bg-white border border-slate-200 text-xs rounded-lg shadow-lg pointer-events-none"
                    style={{
                        top: tooltipStyle.top,
                        bottom: tooltipStyle.showAbove ? tooltipStyle.bottom : undefined,
                        left: tooltipStyle.left,
                    }}
                >
                    {/* Arrow */}
                    <div
                        className={`absolute left-1/2 -translate-x-1/2 w-2 h-2 bg-white border-slate-200 rotate-45 ${
                            tooltipStyle.showAbove ? '-bottom-1 border-r border-b' : '-top-1 border-l border-t'
                        }`}
                    />

                    {/* Content */}
                    <div className="relative">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2">
                            <div className="flex items-center gap-2">
                                <div className={`w-2 h-2 rounded-full ${config.color}`} />
                                <span className="font-semibold text-slate-900">
                                    {t(`shm.status.${status}`, config.label)}
                                </span>
                            </div>
                        </div>

                        {status === 'nominal' && (
                            <>
                                <p className="text-slate-500 mb-2">
                                    {t('shm.status.nominalDesc', 'Vibration patterns are within expected bounds.')}
                                </p>
                                <div className="space-y-1">
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">{t('shm.status.peakFreq', 'Peak frequency')}</span>
                                        <span className="font-medium text-slate-700">1.12 - 1.18 Hz</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">{t('shm.status.expected', 'Expected')}</span>
                                        <span className="font-medium text-slate-700">1.05 - 1.20 Hz</span>
                                    </div>
                                </div>
                            </>
                        )}

                        {status === 'warning' && (
                            <>
                                <p className="text-slate-500 mb-2">
                                    {t('shm.status.warningDesc', 'Minor deviations detected. Monitoring closely.')}
                                </p>
                                <div className="space-y-1">
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">{t('shm.status.deviation', 'Deviation')}</span>
                                        <span className="font-medium text-amber-600">+5%</span>
                                    </div>
                                </div>
                            </>
                        )}

                        {status === 'critical' && (
                            <>
                                <p className="text-slate-500 mb-2">
                                    {t('shm.status.criticalDesc', 'Significant anomaly detected. Review recommended.')}
                                </p>
                                <div className="space-y-1">
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">{t('shm.status.deviation', 'Deviation')}</span>
                                        <span className="font-medium text-red-600">+15%</span>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
