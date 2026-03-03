import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSection } from '@/hooks/useSection'
import { usePermissions } from '@/hooks/usePermissions'

function LayersIcon() {
    return (
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path d="M12 2L2 7l10 5 10-5-10-5z" strokeLinejoin="round" />
            <path d="M2 17l10 5 10-5" strokeLinejoin="round" />
            <path d="M2 12l10 5 10-5" strokeLinejoin="round" />
        </svg>
    )
}

/* ── Reusable row: colored dot + label + on/off ── */

type LayerRowProps = {
    label: string
    checked: boolean
    onChange: () => void
    color: string
}

function LayerRow({ label, checked, onChange, color }: LayerRowProps) {
    return (
        <button
            type="button"
            onClick={onChange}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 min-h-[36px] md:min-h-0 hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer transition-colors"
        >
            {/* Colored dot indicator */}
            <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0 transition-opacity"
                style={{ backgroundColor: color, opacity: checked ? 1 : 0.25 }}
            />
            <span className={`text-sm flex-1 text-left transition-colors ${checked ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'}`}>
                {label}
            </span>
            {/* Mini toggle pill */}
            <span
                className={`
                    w-7 h-4 rounded-full flex-shrink-0 relative transition-colors
                    ${checked ? 'bg-slate-600 dark:bg-slate-300' : 'bg-slate-200 dark:bg-slate-700'}
                `}
            >
                <span
                    className={`
                        absolute top-0.5 w-3 h-3 rounded-full bg-white dark:bg-slate-900 shadow-sm transition-[left]
                        ${checked ? 'left-3.5' : 'left-0.5'}
                    `}
                />
            </span>
        </button>
    )
}

/* ── Section header ── */

function SectionLabel({ label }: { label: string }) {
    return (
        <div className="px-3 pt-2 pb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                {label}
            </span>
        </div>
    )
}

/* ── Segmented toggle for detection mode ── */

type SegmentedToggleProps = {
    value: string
    options: { key: string; label: string }[]
    onChange: (key: string) => void
}

function SegmentedToggle({ value, options, onChange }: SegmentedToggleProps) {
    return (
        <div className="px-3 py-1.5">
            <div className="flex gap-px p-0.5 rounded-lg bg-slate-100 dark:bg-slate-800">
                {options.map(opt => {
                    const active = value === opt.key
                    return (
                        <button
                            type="button"
                            key={opt.key}
                            onClick={() => onChange(opt.key)}
                            className={`
                                flex-1 px-2 py-1 text-xs font-medium rounded-md transition-all cursor-pointer whitespace-nowrap
                                ${active
                                    ? 'bg-white dark:bg-slate-600 text-slate-800 dark:text-slate-100 shadow-sm'
                                    : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'
                                }
                            `}
                        >
                            {opt.label}
                        </button>
                    )
                })}
            </div>
        </div>
    )
}

function Divider() {
    return <div className="my-1 mx-3 border-t border-slate-100 dark:border-slate-800" />
}

/* ── Main component ── */

export function MapControls() {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)
    const containerRef = useRef<HTMLDivElement>(null)
    const { layerVisibility, setLayerVisibility, sectionCreationMode, setSectionCreationMode, pendingPoint } = useSection()
    const { hasLayer } = usePermissions()

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false)
            }
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    const toggle = (layer: keyof typeof layerVisibility) => {
        setLayerVisibility({ ...layerVisibility, [layer]: !layerVisibility[layer] })
    }

    // Detection mode: vehicles / dots / off
    const detectionMode =
        layerVisibility.vehicles ? 'vehicles'
        : layerVisibility.detections ? 'detections'
        : 'off'

    const setDetectionMode = (mode: string) => {
        setLayerVisibility({
            ...layerVisibility,
            vehicles: mode === 'vehicles',
            detections: mode === 'detections',
        })
    }

    const startSectionCreation = () => {
        setSectionCreationMode(true)
        setOpen(false)
    }

    const isCreatingSection = sectionCreationMode || pendingPoint !== null

    // Any layers at all?
    const hasAnyLayer = hasLayer('cables') || hasLayer('fibers') || hasLayer('vehicles')
        || hasLayer('detections') || hasLayer('heatmap') || hasLayer('landmarks')
        || hasLayer('sections') || hasLayer('infrastructure') || hasLayer('incidents')

    if (!hasAnyLayer) return null

    return (
        <div ref={containerRef} className="absolute top-3 left-3 z-[1000] pointer-events-auto">
            <button
                onClick={() => setOpen(!open)}
                className={`
                    w-11 h-11 md:w-[29px] md:h-[29px] flex items-center justify-center rounded shadow-md cursor-pointer transition-colors touch-none
                    ${open ? 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300' : 'bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'}
                `}
                title={t('map.layers')}
            >
                <LayersIcon />
            </button>

            {open && (
                <div className="absolute top-[calc(100%+4px)] left-0 bg-white dark:bg-slate-900 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 py-1.5 min-w-[200px] select-none">

                    {/* ── Fiber layers ── */}
                    {(hasLayer('cables') || hasLayer('fibers')) && (
                        <>
                            <SectionLabel label={t('map.controls.baseLayers')} />
                            {hasLayer('cables') && (
                                <LayerRow label={t('map.controls.cables')} checked={layerVisibility.cables} onChange={() => toggle('cables')} color="#f97316" />
                            )}
                            {hasLayer('fibers') && (
                                <LayerRow label={t('map.controls.fiberLines')} checked={layerVisibility.fibers} onChange={() => toggle('fibers')} color="#9ca3af" />
                            )}
                        </>
                    )}

                    {/* ── Detection visualization ── */}
                    {(hasLayer('vehicles') || hasLayer('detections')) && (
                        <>
                            <Divider />
                            <SectionLabel label={t('map.controls.detectionMode')} />
                            <SegmentedToggle
                                value={detectionMode}
                                onChange={setDetectionMode}
                                options={[
                                    { key: 'vehicles', label: t('map.controls.vehicles') },
                                    { key: 'off', label: 'Off' },
                                    { key: 'detections', label: t('map.controls.detections') },
                                ]}
                            />
                        </>
                    )}

                    {/* ── Heatmap ── */}
                    {hasLayer('heatmap') && (
                        <>
                            <Divider />
                            <LayerRow label={t('map.controls.speedHeatmap')} checked={layerVisibility.heatmap} onChange={() => toggle('heatmap')} color="#f43f5e" />
                        </>
                    )}

                    {/* ── Annotations ── */}
                    {(hasLayer('landmarks') || hasLayer('sections') || hasLayer('infrastructure') || hasLayer('incidents')) && (
                        <>
                            <Divider />
                            <SectionLabel label={t('map.controls.labels')} />
                            {hasLayer('landmarks') && (
                                <LayerRow label={t('map.controls.landmarks')} checked={layerVisibility.landmarks} onChange={() => toggle('landmarks')} color="#3b82f6" />
                            )}
                            {hasLayer('sections') && (
                                <LayerRow label={t('map.controls.sections')} checked={layerVisibility.sections} onChange={() => toggle('sections')} color="#22c55e" />
                            )}
                            {hasLayer('infrastructure') && (
                                <LayerRow label={t('map.controls.infrastructure')} checked={layerVisibility.infrastructure} onChange={() => toggle('infrastructure')} color="#f59e0b" />
                            )}
                            {hasLayer('incidents') && (
                                <LayerRow label={t('map.controls.incidents')} checked={layerVisibility.incidents} onChange={() => toggle('incidents')} color="#ef4444" />
                            )}
                        </>
                    )}

                    {/* ── Actions ── */}
                    {hasLayer('sections') && (
                        <>
                            <Divider />
                            <button
                                onClick={startSectionCreation}
                                disabled={isCreatingSection}
                                className={`
                                    w-full px-3 py-1.5 text-left text-sm min-h-[36px] md:min-h-0 transition-colors
                                    ${isCreatingSection
                                        ? 'text-amber-600 dark:text-amber-500 bg-amber-50 dark:bg-amber-950 cursor-default'
                                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer'
                                    }
                                `}
                            >
                                {isCreatingSection ? t('map.controls.clickFiberToStart') : t('map.controls.newSection')}
                            </button>
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
