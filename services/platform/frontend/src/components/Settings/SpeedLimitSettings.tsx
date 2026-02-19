import { useState, useMemo, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useFibers } from '@/hooks/useFibers'
import { useSpeedLimits } from '@/hooks/useSpeedLimits'
import { FiberPreviewMap } from './FiberPreviewMap'
import type { SpeedLimitZone } from '@/types/speedLimit'

type ZoneRowProps = {
    zone: SpeedLimitZone
    maxChannel: number
    onUpdate: (updates: Partial<Pick<SpeedLimitZone, 'startChannel' | 'endChannel' | 'limit'>>) => void
    onDelete: () => void
}

function ZoneRow({ zone, maxChannel, onUpdate, onDelete }: ZoneRowProps) {
    const { t } = useTranslation()
    // Local state for inputs - only commits on blur to prevent ID changes during typing
    const [localStart, setLocalStart] = useState(String(zone.startChannel))
    const [localEnd, setLocalEnd] = useState(String(zone.endChannel))
    const [localLimit, setLocalLimit] = useState(String(zone.limit))

    // Sync local state when zone changes from external source
    useEffect(() => {
        setLocalStart(String(zone.startChannel))
        setLocalEnd(String(zone.endChannel))
        setLocalLimit(String(zone.limit))
    }, [zone.startChannel, zone.endChannel, zone.limit])

    const commitField = (field: 'start' | 'end' | 'limit') => {
        if (field === 'start') {
            const value = parseInt(localStart) || 0
            if (value !== zone.startChannel) {
                onUpdate({ startChannel: value })
            }
        } else if (field === 'end') {
            const value = parseInt(localEnd) || 0
            if (value !== zone.endChannel) {
                onUpdate({ endChannel: value })
            }
        } else {
            const value = parseInt(localLimit) || 50
            if (value !== zone.limit) {
                onUpdate({ limit: value })
            }
        }
    }

    const handleKeyDown = (field: 'start' | 'end' | 'limit', e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            commitField(field)
            ;(e.target as HTMLInputElement).blur()
        }
    }

    return (
        <div className="flex items-center gap-2">
            <div className="flex-1 grid grid-cols-3 gap-2">
                <input
                    type="number"
                    value={localStart}
                    onChange={(e) => setLocalStart(e.target.value)}
                    onBlur={() => commitField('start')}
                    onKeyDown={(e) => handleKeyDown('start', e)}
                    min={0}
                    max={maxChannel}
                    className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder={t('settings.speed.startPlaceholder')}
                />
                <input
                    type="number"
                    value={localEnd}
                    onChange={(e) => setLocalEnd(e.target.value)}
                    onBlur={() => commitField('end')}
                    onKeyDown={(e) => handleKeyDown('end', e)}
                    min={0}
                    max={maxChannel}
                    className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder={t('settings.speed.endPlaceholder')}
                />
                <div className="flex items-center gap-1">
                    <input
                        type="number"
                        value={localLimit}
                        onChange={(e) => setLocalLimit(e.target.value)}
                        onBlur={() => commitField('limit')}
                        onKeyDown={(e) => handleKeyDown('limit', e)}
                        min={1}
                        max={300}
                        className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder={t('settings.speed.limitPlaceholder')}
                    />
                    <span className="text-xs text-slate-500 whitespace-nowrap">km/h</span>
                </div>
            </div>
            <button
                onClick={onDelete}
                className="p-1.5 text-slate-400 hover:text-red-500 transition-colors"
                title={t('settings.speed.deleteZone')}
            >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
    )
}

export function SpeedLimitSettings() {
    const { t } = useTranslation()
    const { fibers, loading } = useFibers()
    const { addZone, updateZone, deleteZone, getZonesForFiber } = useSpeedLimits()
    const [selectedFiberId, setSelectedFiberId] = useState<string>('')

    // Select first fiber by default when loaded
    const selectedFiber = useMemo(() => {
        if (selectedFiberId) {
            return fibers.find(f => f.id === selectedFiberId)
        }
        if (fibers.length > 0 && !selectedFiberId) {
            return fibers[0]
        }
        return null
    }, [fibers, selectedFiberId])

    // Auto-select first fiber
    if (fibers.length > 0 && !selectedFiberId) {
        setSelectedFiberId(fibers[0].id)
    }

    const fiberZones = useMemo(() => {
        if (!selectedFiber) return []
        return getZonesForFiber(selectedFiber.id)
    }, [selectedFiber, getZonesForFiber])

    const handleAddZone = () => {
        if (!selectedFiber) return

        // Find a gap or add at the end
        const maxChannel = selectedFiber.coordinates.length - 1
        let start = 0
        let end = Math.min(100, maxChannel)

        if (fiberZones.length > 0) {
            const lastZone = fiberZones[fiberZones.length - 1]
            start = lastZone.endChannel + 1
            end = Math.min(start + 100, maxChannel)
        }

        if (start <= maxChannel) {
            addZone(selectedFiber.id, start, end, 50)
        }
    }

    if (loading) {
        return <div className="text-slate-500">{t('settings.speed.loadingFibers')}</div>
    }

    if (fibers.length === 0) {
        return <div className="text-slate-500">{t('settings.speed.noFibers')}</div>
    }

    return (
        <div className="flex gap-6">
            {/* Left: Zone Editor */}
            <div className="flex-1 min-w-0">
                {/* Fiber Selection */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                        {t('settings.speed.selectFiber')}
                    </label>
                    <select
                        value={selectedFiberId}
                        onChange={(e) => setSelectedFiberId(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {fibers.map(fiber => (
                            <option key={fiber.id} value={fiber.id}>
                                {fiber.name} ({fiber.coordinates.length} {t('settings.speed.channels')})
                            </option>
                        ))}
                    </select>
                </div>

                {/* Zone List */}
                <div className="mb-4">
                    <div className="flex items-center justify-between mb-2">
                        <label className="text-sm font-medium text-slate-700">
                            {t('settings.speed.zones')}
                        </label>
                        <span className="text-xs text-slate-400">
                            {t('settings.speed.channelRange', { max: selectedFiber ? selectedFiber.coordinates.length - 1 : 0 })}
                        </span>
                    </div>

                    {/* Header */}
                    <div className="grid grid-cols-3 gap-2 mb-2 pr-8">
                        <span className="text-xs text-slate-500">{t('settings.speed.startChannel')}</span>
                        <span className="text-xs text-slate-500">{t('settings.speed.endChannel')}</span>
                        <span className="text-xs text-slate-500">{t('settings.speed.speedLimit')}</span>
                    </div>

                    {/* Zone Rows */}
                    <div className="space-y-2">
                        {fiberZones.length === 0 ? (
                            <div className="text-sm text-slate-400 py-4 text-center border border-dashed border-slate-200 rounded">
                                {t('settings.speed.noZones')}
                                <br />
                                {t('settings.speed.noZonesHint')}
                            </div>
                        ) : (
                            fiberZones.map(zone => (
                                <ZoneRow
                                    key={zone.id}
                                    zone={zone}
                                    maxChannel={selectedFiber?.coordinates.length ?? 0}
                                    onUpdate={(updates) => updateZone(zone.id, updates)}
                                    onDelete={() => deleteZone(zone.id)}
                                />
                            ))
                        )}
                    </div>

                    {/* Add Button */}
                    <button
                        onClick={handleAddZone}
                        className="mt-3 px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded transition-colors flex items-center gap-1"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                        {t('settings.speed.addZone')}
                    </button>
                </div>

                {/* Info */}
                <div className="text-xs text-slate-400 space-y-1">
                    <p>{t('settings.speed.coloringInfo')}</p>
                    <div className="flex items-center gap-3 mt-2">
                        <span className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#22c55e' }}></span>
                            80%+
                        </span>
                        <span className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#84cc16' }}></span>
                            60-80%
                        </span>
                        <span className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#eab308' }}></span>
                            40-60%
                        </span>
                        <span className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#f97316' }}></span>
                            20-40%
                        </span>
                        <span className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#ef4444' }}></span>
                            &lt;20%
                        </span>
                    </div>
                </div>
            </div>

            {/* Right: Preview Map */}
            <div className="w-80 flex-shrink-0">
                <label className="block text-sm font-medium text-slate-700 mb-1">
                    {t('settings.speed.preview')}
                </label>
                <div className="h-64 border border-slate-200 rounded-lg overflow-hidden">
                    {selectedFiber && (
                        <FiberPreviewMap
                            fiber={selectedFiber}
                            zones={fiberZones}
                        />
                    )}
                </div>
                {/* Legend */}
                <div className="mt-2 space-y-1">
                    {fiberZones.map(zone => (
                        <div key={zone.id} className="flex items-center gap-2 text-xs text-slate-600">
                            <span
                                className="w-3 h-3 rounded"
                                style={{ backgroundColor: getLimitColor(zone.limit) }}
                            ></span>
                            <span>Ch {zone.startChannel}-{zone.endChannel}: {zone.limit} km/h</span>
                        </div>
                    ))}
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                        <span className="w-3 h-3 rounded bg-slate-300"></span>
                        <span>{t('settings.speed.noLimitDefined')}</span>
                    </div>
                </div>
            </div>
        </div>
    )
}

// Color for each limit range (for legend/preview)
function getLimitColor(limit: number): string {
    if (limit >= 100) return '#3b82f6' // blue - highway
    if (limit >= 70) return '#8b5cf6'  // purple - fast road
    if (limit >= 50) return '#f59e0b'  // amber - urban
    return '#ef4444'                    // red - slow zone
}
