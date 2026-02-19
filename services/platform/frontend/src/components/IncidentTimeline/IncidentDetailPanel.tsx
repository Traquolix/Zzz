import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import mapboxgl from 'mapbox-gl'
import type { Incident } from '@/types/incident'
import { useIncidentSnapshot } from '@/hooks/useIncidentSnapshot'
import { useFibers } from '@/hooks/useFibers'
import { SnapshotChart } from './SnapshotChart'
import { AlertTriangle, TrendingDown, TrafficCone, HelpCircle, X, CheckCircle, Loader2 } from 'lucide-react'
import { SEVERITY_DETAIL } from '@/constants/incidents'

type Props = {
    incident: Incident
    onClose: () => void
}

// Delay rendering of size-sensitive components until after slide animation
const ANIMATION_DELAY = 350

const TYPE_ICONS = {
    slowdown: TrendingDown,
    congestion: TrafficCone,
    accident: AlertTriangle,
    anomaly: HelpCircle,
}

const SEVERITY_COLORS = SEVERITY_DETAIL

function formatDateTime(dateStr: string): string {
    const date = new Date(dateStr)
    return date.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    })
}

function formatDuration(ms: number): string {
    const minutes = Math.floor(ms / 60000)
    const hours = Math.floor(minutes / 60)
    if (hours > 0) {
        return `${hours}h ${minutes % 60}m`
    }
    return `${minutes}m`
}

export function IncidentDetailPanel({ incident, onClose }: Props) {
    const { t } = useTranslation()
    const mapContainerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<mapboxgl.Map | null>(null)
    const [isReady, setIsReady] = useState(false)
    const { snapshot, loading, error, fetchSnapshot } = useIncidentSnapshot()
    const { getPosition, fibers } = useFibers()

    const Icon = TYPE_ICONS[incident.type]
    const isResolved = incident.status === 'resolved'
    const position = getPosition(incident.fiberLine, incident.channel, 0)

    // Wait for slide animation to complete before rendering size-sensitive components
    useEffect(() => {
        const timer = setTimeout(() => setIsReady(true), ANIMATION_DELAY)
        return () => clearTimeout(timer)
    }, [])

    // Fetch snapshot on mount
    useEffect(() => {
        fetchSnapshot(incident.id)
    }, [incident.id, fetchSnapshot])

    // Initialize mini map - only after animation is complete and fibers are loaded
    useEffect(() => {
        if (!mapContainerRef.current || !position || !isReady || fibers.length === 0) return

        const fiber = fibers.find(f => f.id === incident.fiberLine)

        const incidentCenter: [number, number] = [position.lng, position.lat]

        const map = new mapboxgl.Map({
            container: mapContainerRef.current,
            style: 'mapbox://styles/mapbox/light-v11',
            center: incidentCenter,
            zoom: 11,
            attributionControl: false,
            dragPan: false,
            dragRotate: false,
            touchZoomRotate: false,
            doubleClickZoom: false,
            scrollZoom: {
                around: 'center'
            },
        })

        mapRef.current = map

        map.on('load', () => {
            // Add fiber line - coordinates are already [lng, lat] tuples
            if (fiber && fiber.coordinates.length > 0) {
                map.addSource('fiber-line', {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        properties: {},
                        geometry: {
                            type: 'LineString',
                            coordinates: fiber.coordinates // Already [lng, lat][] format
                        }
                    }
                })

                // Fiber line glow effect
                map.addLayer({
                    id: 'fiber-line-glow',
                    type: 'line',
                    source: 'fiber-line',
                    paint: {
                        'line-color': '#3b82f6',
                        'line-width': 10,
                        'line-opacity': 0.3,
                        'line-blur': 4
                    }
                })

                // Fiber line main
                map.addLayer({
                    id: 'fiber-line',
                    type: 'line',
                    source: 'fiber-line',
                    paint: {
                        'line-color': '#3b82f6',
                        'line-width': 4,
                        'line-opacity': 1
                    }
                })
            }

            // Add incident marker with inline styles (Tailwind classes don't work in raw HTML)
            const markerEl = document.createElement('div')
            markerEl.style.cssText = `
                width: 24px;
                height: 24px;
                background-color: #ef4444;
                border: 3px solid white;
                border-radius: 50%;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                display: flex;
                align-items: center;
                justify-content: center;
                animation: pulse 2s infinite;
            `
            const innerDot = document.createElement('div')
            innerDot.style.cssText = `
                width: 8px;
                height: 8px;
                background-color: white;
                border-radius: 50%;
            `
            markerEl.appendChild(innerDot)

            new mapboxgl.Marker(markerEl)
                .setLngLat([position.lng, position.lat])
                .addTo(map)
        })

        return () => {
            map.remove()
            mapRef.current = null
        }
    }, [position, incident.fiberLine, incident.channel, fibers, isReady])

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Header */}
            <div className="px-6 py-4 border-b flex items-start justify-between">
                <div className="flex items-start gap-3">
                    <div className={`p-2 rounded-lg ${SEVERITY_COLORS[incident.severity]}`}>
                        <Icon className="h-5 w-5" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h2 className="text-lg font-semibold text-slate-900">
                                {t(`incidents.types.${incident.type}`)}
                            </h2>
                            {isResolved && (
                                <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                                    <CheckCircle className="h-3 w-3" />
                                    {t('incidents.resolved')}
                                </span>
                            )}
                        </div>
                        <div className="text-sm text-slate-500 mt-0.5">
                            {formatDateTime(incident.detectedAt)}
                        </div>
                    </div>
                </div>
                <button
                    onClick={onClose}
                    className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                    aria-label={t('incidents.closeDetail')}
                >
                    <X className="h-5 w-5" aria-hidden="true" />
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
                {/* Details */}
                <div className="px-6 py-4 border-b">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">{t('common.severity')}</div>
                            <div className={`inline-block px-2 py-0.5 rounded text-sm font-medium capitalize ${SEVERITY_COLORS[incident.severity]}`}>
                                {incident.severity}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">{t('common.duration')}</div>
                            <div className="text-sm font-medium text-slate-700">
                                {incident.duration ? formatDuration(incident.duration) : t('incidents.ongoing')}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">{t('incidents.fiberLine')}</div>
                            <div className="text-sm font-medium text-slate-700">{incident.fiberLine}</div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">{t('common.channel')}</div>
                            <div className="text-sm font-medium text-slate-700">{incident.channel}</div>
                        </div>
                    </div>
                </div>

                {/* Map */}
                <div className="px-6 py-4 border-b">
                    <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">{t('common.location')}</div>
                    {isReady ? (
                        <div
                            ref={mapContainerRef}
                            className="h-48 rounded-lg overflow-hidden border border-slate-200"
                        />
                    ) : (
                        <div className="h-48 rounded-lg border border-slate-200 bg-slate-50 flex items-center justify-center">
                            <Loader2 className="h-5 w-5 animate-spin text-slate-300" />
                        </div>
                    )}
                </div>

                {/* Snapshot Chart */}
                <div className="px-6 py-4">
                    <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">{t('common.trafficSnapshot')}</div>
                    {!isReady || loading ? (
                        <div className="h-48 flex items-center justify-center text-slate-400">
                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                            {!isReady ? '' : t('incidents.loadingSnapshot')}
                        </div>
                    ) : error ? (
                        <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
                            {error}
                        </div>
                    ) : snapshot ? (
                        <SnapshotChart snapshot={snapshot} height={160} />
                    ) : (
                        <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
                            {t('common.noSnapshot')}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
