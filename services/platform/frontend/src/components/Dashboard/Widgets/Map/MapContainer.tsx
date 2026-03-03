import { useEffect, useRef, useState, useContext, type ReactNode } from 'react'
import mapboxgl from 'mapbox-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MapContext } from './MapContext'
import { MapInstanceContext } from '@/context/MapInstanceContext'
import { MAPBOX_TOKEN } from '@/config/mapbox'

mapboxgl.accessToken = MAPBOX_TOKEN

type Props = {
    children: ReactNode
    center?: [number, number]
    zoom?: number
    pitch?: number
    bearing?: number
}

export function MapContainer({
                                 children,
                                 center = [7.26, 43.7],
                                 zoom = 14,
                                 pitch = 60,
                                 bearing = -20
                             }: Props) {
    const mapContainerRef = useRef<HTMLDivElement>(null)
    const mapRef = useRef<mapboxgl.Map | null>(null)
    const overlayRef = useRef<MapboxOverlay | null>(null)
    const [ready, setReady] = useState(false)

    const [mapInstance, setMapInstance] = useState<mapboxgl.Map | null>(null)
    const [overlay, setOverlay] = useState<MapboxOverlay | null>(null)

    // Register map with dashboard-level context (if available)
    // Use ref to avoid re-running effect when context changes
    const dashboardMapContext = useContext(MapInstanceContext)
    const dashboardMapContextRef = useRef(dashboardMapContext)
    useEffect(() => {
        dashboardMapContextRef.current = dashboardMapContext
    }, [dashboardMapContext])

    useEffect(() => {
        if (!mapContainerRef.current) return

        const isDark = document.documentElement.classList.contains('dark')
        const mapInstance = new mapboxgl.Map({
            container: mapContainerRef.current,
            style: isDark ? 'mapbox://styles/mapbox/dark-v11' : 'mapbox://styles/mapbox/light-v11',
            center,
            zoom,
            pitch,
            bearing,
            antialias: true,
            collectResourceTiming: false,
            attributionControl: false
        })

        mapRef.current = mapInstance

        // Disable double-click zoom (we use double-click for editing labels)
        mapInstance.doubleClickZoom.disable()

        mapInstance.addControl(new mapboxgl.AttributionControl(), 'bottom-right')
        mapInstance.addControl(new mapboxgl.NavigationControl(), 'top-right')

        mapInstance.once('style.load', () => {
            requestAnimationFrame(() => {
                mapInstance.resize()
            })

            const deckOverlay = new MapboxOverlay({
                interleaved: true,
                layers: []
            })

            mapInstance.addControl(deckOverlay as unknown as mapboxgl.IControl)
            overlayRef.current = deckOverlay

            setMapInstance(mapInstance)
            setOverlay(deckOverlay)
            requestAnimationFrame(() => {
                setReady(true)
            })

            // Register with dashboard-level context
            if (dashboardMapContextRef.current) {
                dashboardMapContextRef.current.setMapInstance(mapInstance)
            }
        })

        // Observe dark mode changes
        const observer = new MutationObserver(() => {
            const nowDark = document.documentElement.classList.contains('dark')
            const targetStyle = nowDark ? 'mapbox://styles/mapbox/dark-v11' : 'mapbox://styles/mapbox/light-v11'
            if (mapRef.current) {
                mapRef.current.setStyle(targetStyle)
            }
        })
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

        let resizeRafId: number | null = null
        const scheduleResize = () => {
            if (resizeRafId !== null) return
            resizeRafId = requestAnimationFrame(() => {
                resizeRafId = null
                mapInstance.resize()
            })
        }

        const resizer = new ResizeObserver(() => {
            scheduleResize()
        })

        resizer.observe(mapContainerRef.current)

        return () => {
            // Clear state first to prevent any renders during cleanup
            setReady(false)
            setMapInstance(null)
            setOverlay(null)

            // Unregister from dashboard-level context
            if (dashboardMapContextRef.current) {
                dashboardMapContextRef.current.setMapInstance(null)
            }

            // Stop observers and pending rAF
            observer.disconnect()
            resizer.disconnect()
            if (resizeRafId !== null) cancelAnimationFrame(resizeRafId)

            // Finalize deck.gl overlay first - this stops its internal animation loop
            if (overlayRef.current) {
                try {
                    overlayRef.current.finalize()
                } catch {
                    // Ignore errors during cleanup
                }
                overlayRef.current = null
            }

            // Then remove the map
            if (mapRef.current) {
                try {
                    mapRef.current.stop() // Stop any pending renders
                    mapRef.current.remove()
                } catch {
                    // Ignore errors during cleanup
                }
                mapRef.current = null
            }
        }
    }, [])

    return (
        <div className="w-full h-full flex flex-col relative">
            <div ref={mapContainerRef} className="flex-1" />
            {ready && mapInstance && overlay && (
                <MapContext.Provider value={{ map: mapInstance, deckOverlay: overlay }}>
                    {/* Overlay container for UI elements that sit on top of the map */}
                    <div className="absolute inset-0 pointer-events-none z-[1000] overflow-hidden">
                        {children}
                    </div>
                </MapContext.Provider>
            )}
        </div>
    )
}