import { useState, useEffect, useCallback } from 'react'
import type { FiberLine } from '@/types/fiber'
import { fetchFibers } from '@/api/fibers'
import { DIRECTION_OFFSET_METERS } from '@/lib/geoUtils'

// Shared cache: all useFibers() instances share a single fetch.
// TTL prevents stale data when fiber config changes (e.g., new cable deployed).
let _cache: FiberLine[] | null = null
let _cacheTime = 0
let _pending: Promise<FiberLine[]> | null = null
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

function isCacheStale(): boolean {
    return !_cache || (Date.now() - _cacheTime) > CACHE_TTL_MS
}

function getCachedFibers(): Promise<FiberLine[]> {
    if (_cache && !isCacheStale()) return Promise.resolve(_cache)
    if (!_pending) {
        _pending = fetchFibers().then(response => {
            _cache = response.results
            _cacheTime = Date.now()
            _pending = null
            return response.results
        }).catch(err => {
            _pending = null
            throw err
        })
    }
    return _pending
}

/** Force cache invalidation (e.g., after admin fiber config change). */
export function invalidateFiberCache(): void {
    _cache = null
    _cacheTime = 0
    _pending = null
}

// Meters per degree at ~43.7° latitude
const METERS_PER_DEG_LNG = 111_320 * Math.cos(43.7 * Math.PI / 180)
const METERS_PER_DEG_LAT = 110_540

export function useFibers() {
    const [fibers, setFibers] = useState<FiberLine[]>(_cache ?? [])
    const [loading, setLoading] = useState(!_cache)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (_cache && !isCacheStale()) {
            setFibers(_cache)
            setLoading(false)
            return
        }
        let cancelled = false
        getCachedFibers()
            .then(data => { if (!cancelled) setFibers(data) })
            .catch(err => { if (!cancelled) setError(err.message) })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [])

    const getPosition = useCallback((fiberLine: string, channel: number, direction: 0 | 1) => {
        const fiber = fibers.find(f => f.id === fiberLine)
        if (!fiber) return null

        const idx = Math.round(channel)
        const coord = fiber.coordinates[idx]
        if (!coord || coord[0] == null || coord[1] == null) return null

        const [lng, lat] = coord

        // Compute bearing from adjacent points
        let bearing = 0
        if (idx < fiber.coordinates.length - 1) {
            const next = fiber.coordinates[idx + 1]
            if (next && next[0] != null && next[1] != null) {
                bearing = Math.atan2(next[0] - lng, next[1] - lat) * 180 / Math.PI
            }
        }

        // If coordinates are precomputed, use them directly without offset
        if (fiber.coordsPrecomputed) {
            return {
                lat,
                lng,
                heading: direction === 0 ? bearing : (bearing + 180) % 360
            }
        }

        // Apply perpendicular offset based on fiber direction
        const offset = fiber.direction === 0
            ? +DIRECTION_OFFSET_METERS
            : -DIRECTION_OFFSET_METERS

        // Perpendicular direction (rotate 90° clockwise)
        let dx = 0, dy = 0
        if (idx < fiber.coordinates.length - 1) {
            const next = fiber.coordinates[idx + 1]
            if (next && next[0] != null && next[1] != null) {
                dx = next[0] - lng
                dy = next[1] - lat
            }
        } else if (idx > 0) {
            const prev = fiber.coordinates[idx - 1]
            if (prev && prev[0] != null && prev[1] != null) {
                dx = lng - prev[0]
                dy = lat - prev[1]
            }
        }

        let offsetLng = lng
        let offsetLat = lat
        const len = Math.sqrt(dx * dx + dy * dy)
        if (len > 0) {
            const nx = dy / len  // perpendicular
            const ny = -dx / len
            offsetLng += nx * offset / METERS_PER_DEG_LNG
            offsetLat += ny * offset / METERS_PER_DEG_LAT
        }

        return {
            lat: offsetLat,
            lng: offsetLng,
            heading: direction === 0 ? bearing : (bearing + 180) % 360
        }
    }, [fibers])

    return { fibers, getPosition, loading, error }
}
