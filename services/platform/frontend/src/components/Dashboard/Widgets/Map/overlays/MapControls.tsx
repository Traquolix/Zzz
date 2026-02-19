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

function ChevronIcon({ expanded }: { expanded: boolean }) {
    return (
        <svg
            className={`w-3 h-3 transition-transform ${expanded ? 'rotate-90' : ''}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
        >
            <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
}

type ToggleRowProps = {
    label: string
    checked: boolean
    onChange: () => void
    color: string
    indent?: boolean
}

function ToggleRow({ label, checked, onChange, color, indent = false }: ToggleRowProps) {
    return (
        <button
            type="button"
            onClick={onChange}
            className={`w-full flex items-center gap-3 px-3 py-1.5 hover:bg-slate-50 cursor-pointer transition-colors ${indent ? 'pl-7' : ''}`}
        >
            <div
                className="w-4 h-4 rounded border-2 flex items-center justify-center transition-colors"
                style={checked
                    ? { backgroundColor: color, borderColor: color }
                    : { borderColor: '#cbd5e1' }
                }
            >
                {checked && (
                    <svg className="w-3 h-3 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} aria-hidden="true">
                        <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                )}
            </div>
            <span className="text-sm text-slate-700">{label}</span>
        </button>
    )
}

type FolderProps = {
    label: string
    expanded: boolean
    onToggle: () => void
    children: React.ReactNode
}

function Folder({ label, expanded, onToggle, children }: FolderProps) {
    return (
        <div>
            <button
                type="button"
                onClick={onToggle}
                className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 cursor-pointer transition-colors"
            >
                <ChevronIcon expanded={expanded} />
                <span className="text-sm font-medium text-slate-600">{label}</span>
            </button>
            {expanded && (
                <div className="pb-1">
                    {children}
                </div>
            )}
        </div>
    )
}

export function MapControls() {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)
    const [expandedFolders, setExpandedFolders] = useState({
        baseLayers: true,
        labels: false,
        overlays: true
    })
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

    const toggleFolder = (folder: keyof typeof expandedFolders) => {
        setExpandedFolders(prev => ({ ...prev, [folder]: !prev[folder] }))
    }

    const toggleLayer = (layer: keyof typeof layerVisibility) => {
        setLayerVisibility({
            ...layerVisibility,
            [layer]: !layerVisibility[layer]
        })
    }

    const startSectionCreation = () => {
        setSectionCreationMode(true)
        setOpen(false)
    }

    const isCreatingSection = sectionCreationMode || pendingPoint !== null

    const hasBaseLayers = hasLayer('cables') || hasLayer('fibers') || hasLayer('vehicles') || hasLayer('heatmap')
    const hasLabels = hasLayer('landmarks') || hasLayer('sections') || hasLayer('infrastructure')
    const hasOverlays = hasLayer('detections') || hasLayer('incidents')

    return (
        <div ref={containerRef} className="absolute top-3 left-3 z-[1000] pointer-events-auto">
            <button
                onClick={() => setOpen(!open)}
                className={`
                    w-[29px] h-[29px] flex items-center justify-center rounded shadow-md cursor-pointer transition-colors
                    ${open ? 'bg-slate-100 text-slate-700' : 'bg-white text-slate-500 hover:bg-slate-50'}
                `}
                title={t('map.layers')}
            >
                <LayersIcon />
            </button>

            {open && (
                <div className="absolute top-[calc(100%+4px)] left-0 bg-white rounded-lg shadow-lg border border-slate-200 py-1 min-w-[180px] select-none">
                    {hasBaseLayers && (
                        <>
                            <Folder
                                label={t('map.controls.baseLayers')}
                                expanded={expandedFolders.baseLayers}
                                onToggle={() => toggleFolder('baseLayers')}
                            >
                                {hasLayer('cables') && (
                                    <ToggleRow
                                        label={t('map.controls.cables')}
                                        checked={layerVisibility.cables}
                                        onChange={() => toggleLayer('cables')}
                                        color="#64748b"
                                        indent
                                    />
                                )}
                                {hasLayer('fibers') && (
                                    <ToggleRow
                                        label={t('map.controls.fiberLines')}
                                        checked={layerVisibility.fibers}
                                        onChange={() => toggleLayer('fibers')}
                                        color="#6366f1"
                                        indent
                                    />
                                )}
                                {hasLayer('vehicles') && (
                                    <ToggleRow
                                        label={t('map.controls.vehicles')}
                                        checked={layerVisibility.vehicles}
                                        onChange={() => toggleLayer('vehicles')}
                                        color="#14b8a6"
                                        indent
                                    />
                                )}
                                {hasLayer('heatmap') && (
                                    <ToggleRow
                                        label={t('map.controls.speedHeatmap')}
                                        checked={layerVisibility.heatmap}
                                        onChange={() => toggleLayer('heatmap')}
                                        color="#f43f5e"
                                        indent
                                    />
                                )}
                            </Folder>
                            <div className="my-1 border-t border-slate-100" />
                        </>
                    )}

                    {hasLabels && (
                        <>
                            <Folder
                                label={t('map.controls.labels')}
                                expanded={expandedFolders.labels}
                                onToggle={() => toggleFolder('labels')}
                            >
                                {hasLayer('landmarks') && (
                                    <ToggleRow
                                        label={t('map.controls.landmarks')}
                                        checked={layerVisibility.landmarks}
                                        onChange={() => toggleLayer('landmarks')}
                                        color="#3b82f6"
                                        indent
                                    />
                                )}
                                {hasLayer('sections') && (
                                    <ToggleRow
                                        label={t('map.controls.sections')}
                                        checked={layerVisibility.sections}
                                        onChange={() => toggleLayer('sections')}
                                        color="#22c55e"
                                        indent
                                    />
                                )}
                                {hasLayer('infrastructure') && (
                                    <ToggleRow
                                        label={t('map.controls.infrastructure')}
                                        checked={layerVisibility.infrastructure}
                                        onChange={() => toggleLayer('infrastructure')}
                                        color="#f59e0b"
                                        indent
                                    />
                                )}
                            </Folder>
                            <div className="my-1 border-t border-slate-100" />
                        </>
                    )}

                    {hasOverlays && (
                        <>
                            <Folder
                                label={t('map.controls.overlays')}
                                expanded={expandedFolders.overlays}
                                onToggle={() => toggleFolder('overlays')}
                            >
                                {hasLayer('detections') && (
                                    <ToggleRow
                                        label={t('map.controls.detections')}
                                        checked={layerVisibility.detections}
                                        onChange={() => toggleLayer('detections')}
                                        color="#a855f7"
                                        indent
                                    />
                                )}
                                {hasLayer('incidents') && (
                                    <ToggleRow
                                        label={t('map.controls.incidents')}
                                        checked={layerVisibility.incidents}
                                        onChange={() => toggleLayer('incidents')}
                                        color="#f97316"
                                        indent
                                    />
                                )}
                            </Folder>
                            <div className="my-1 border-t border-slate-100" />
                        </>
                    )}

                    {hasLayer('sections') && (
                        <button
                            onClick={startSectionCreation}
                            disabled={isCreatingSection}
                            className={`
                                w-full px-3 py-2 text-left text-sm transition-colors
                                ${isCreatingSection
                                    ? 'text-amber-600 bg-amber-50 cursor-default'
                                    : 'text-slate-700 hover:bg-slate-50 cursor-pointer'
                                }
                            `}
                        >
                            {isCreatingSection ? t('map.controls.clickFiberToStart') : t('map.controls.newSection')}
                        </button>
                    )}
                </div>
            )}
        </div>
    )
}
