import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX_TOKEN } from '@/config/mapbox'
import { MAP_CENTER, MAP_ZOOM } from '../../data'

export function useMapInstance() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    mapboxgl.accessToken = MAPBOX_TOKEN

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      pitch: 30,
      antialias: false,
      fadeDuration: 0,
    })

    mapRef.current = map

    // ResizeObserver with rAF-throttled resize
    let resizeRafId: number | null = null
    const scheduleResize = () => {
      if (resizeRafId !== null) return
      resizeRafId = requestAnimationFrame(() => {
        resizeRafId = null
        map.resize()
      })
    }

    const resizer = new ResizeObserver(() => scheduleResize())
    resizer.observe(containerRef.current)

    return () => {
      resizer.disconnect()
      if (resizeRafId !== null) cancelAnimationFrame(resizeRafId)
      map.remove()
      mapRef.current = null
    }
  }, [])

  return { containerRef, mapRef }
}
