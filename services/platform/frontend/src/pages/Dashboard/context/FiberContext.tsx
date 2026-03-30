import { createContext, useContext, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchFibers, type ApiFiber, type CoverageRange } from '@/api/fibers'
import { getFiberOffsetCoords } from '@/lib/geoUtils'
import type { Fiber } from '../types'

// ── Simplification (ported from data.ts) ────────────────────────────────

const SIMPLIFY_TOLERANCE = 0.000005

function simplifyCoords(coords: [number, number][], tolerance: number): [number, number][] {
  if (coords.length <= 2) return coords

  let maxDist = 0
  let maxIdx = 0
  const [ax, ay] = coords[0]
  const [bx, by] = coords[coords.length - 1]
  const dx = bx - ax
  const dy = by - ay
  const lenSq = dx * dx + dy * dy

  for (let i = 1; i < coords.length - 1; i++) {
    const [px, py] = coords[i]
    let dist: number
    if (lenSq === 0) {
      dist = Math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
    } else {
      const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq))
      const projX = ax + t * dx
      const projY = ay + t * dy
      dist = Math.sqrt((px - projX) ** 2 + (py - projY) ** 2)
    }
    if (dist > maxDist) {
      maxDist = dist
      maxIdx = i
    }
  }

  if (maxDist <= tolerance) {
    return [coords[0], coords[coords.length - 1]]
  }

  const left = simplifyCoords(coords.slice(0, maxIdx + 1), tolerance)
  const right = simplifyCoords(coords.slice(maxIdx), tolerance)
  return [...left.slice(0, -1), ...right]
}

// ── Cache builders ──────────────────────────────────────────────────────

function buildFibersFromApi(apiFibers: ApiFiber[]): Fiber[] {
  return apiFibers.map(af => ({
    id: af.id,
    parentCableId: af.parentFiberId,
    direction: af.direction as 0 | 1,
    name: af.name,
    color: af.color,
    totalChannels: af.coordinates.length,
    coordinates: af.coordinates,
    coordsPrecomputed: af.coordsPrecomputed,
  }))
}

function buildOffsetCache(fibers: Fiber[]) {
  return new Map<string, [number, number][]>(
    fibers.map(f => [f.id, getFiberOffsetCoords({ ...f, coordinates: f.coordinates as [number, number][] })]),
  )
}

function buildRenderCache(fibers: Fiber[], offsetCache: Map<string, [number, number][]>) {
  return new Map<string, [number, number][]>(
    fibers.map(f => {
      const full = offsetCache.get(f.id)!
      return [f.id, simplifyCoords(full, SIMPLIFY_TOLERANCE)]
    }),
  )
}

function buildChannelMaps(fibers: Fiber[]) {
  const channelToOffsetIndex = new Map<string, Map<number, number>>()
  const offsetIndexToChannel = new Map<string, number[]>()

  for (const fiber of fibers) {
    const forward = new Map<number, number>()
    const reverse: number[] = []
    let idx = 0
    for (let ch = 0; ch < fiber.coordinates.length; ch++) {
      const c = fiber.coordinates[ch]
      if (c[0] != null && c[1] != null) {
        forward.set(ch, idx)
        reverse.push(ch)
        idx++
      }
    }
    if (!fiber.coordsPrecomputed) {
      channelToOffsetIndex.set(fiber.id, forward)
    }
    offsetIndexToChannel.set(fiber.id, reverse)
  }

  return { channelToOffsetIndex, offsetIndexToChannel }
}

function buildFiberIndex(fibers: Fiber[]) {
  const index = new Map<string, Map<number, Fiber>>()
  for (const f of fibers) {
    let byDir = index.get(f.parentCableId)
    if (!byDir) {
      byDir = new Map()
      index.set(f.parentCableId, byDir)
    }
    byDir.set(f.direction, f)
  }
  return index
}

function buildCoverageMap(apiFibers: ApiFiber[]) {
  const coverage = new Map<string, CoverageRange[]>()
  for (const af of apiFibers) {
    // Only take direction 0 — coverage is the same for both directions
    if (af.direction === 0 && af.dataCoverage.length > 0) {
      coverage.set(af.parentFiberId, af.dataCoverage)
    }
  }
  return coverage
}

// ── Context type ────────────────────────────────────────────────────────

interface FiberContextType {
  fibers: Fiber[]
  fiberOffsetCache: Map<string, [number, number][]>
  fiberRenderCache: Map<string, [number, number][]>
  offsetIndexToChannel: Map<string, number[]>
  coverageMap: Map<string, CoverageRange[]>
  findFiber: (cableId: string, direction: number) => Fiber | undefined
  channelToCoord: (fiber: Fiber, channel: number) => [number, number] | null
  getSectionCoords: (fiber: Fiber, startChannel: number, endChannel: number) => [number, number][]
  findNearestFiberPoint: (
    lngLat: [number, number],
    maxDistDeg?: number,
    coverageFilter?: Map<string, CoverageRange[]>,
  ) => { fiberId: string; direction: 0 | 1; channel: number; lng: number; lat: number } | null
  buildCoverageRenderCache: (cm: Map<string, CoverageRange[]>) => Map<string, [number, number][][]>
  isLoading: boolean
}

const EMPTY_FIBERS: Fiber[] = []
const EMPTY_MAP = new Map<string, never>()

const FiberContext = createContext<FiberContextType | null>(null)

// ── Provider ────────────────────────────────────────────────────────────

export function FiberProvider({ children }: { children: React.ReactNode }) {
  const { data: apiFibers, isLoading } = useQuery({
    queryKey: ['fibers'],
    queryFn: fetchFibers,
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  })

  const value = useMemo<FiberContextType>(() => {
    if (!apiFibers || apiFibers.length === 0) {
      const noop = () => undefined
      return {
        fibers: EMPTY_FIBERS,
        fiberOffsetCache: EMPTY_MAP as Map<string, [number, number][]>,
        fiberRenderCache: EMPTY_MAP as Map<string, [number, number][]>,
        offsetIndexToChannel: EMPTY_MAP as Map<string, number[]>,
        coverageMap: EMPTY_MAP as Map<string, CoverageRange[]>,
        findFiber: noop,
        channelToCoord: () => null,
        getSectionCoords: () => [],
        findNearestFiberPoint: () => null,
        buildCoverageRenderCache: () => new Map(),
        isLoading,
      }
    }

    const fibers = buildFibersFromApi(apiFibers)
    const fiberOffsetCache = buildOffsetCache(fibers)
    const fiberRenderCache = buildRenderCache(fibers, fiberOffsetCache)
    const { channelToOffsetIndex, offsetIndexToChannel } = buildChannelMaps(fibers)
    const fiberIndex = buildFiberIndex(fibers)
    const coverageMap = buildCoverageMap(apiFibers)

    // ── Closure functions (close over caches) ──

    const findFiber = (cableId: string, direction: number): Fiber | undefined => fiberIndex.get(cableId)?.get(direction)

    const channelToCoord = (fiber: Fiber, channel: number): [number, number] | null => {
      if (channel < 0 || channel >= fiber.coordinates.length) return null

      if (fiber.coordsPrecomputed) {
        const c = fiber.coordinates[channel]
        if (c[0] == null || c[1] == null) return null
        return c as [number, number]
      }

      const idxMap = channelToOffsetIndex.get(fiber.id)
      if (!idxMap) return null
      const offsetIdx = idxMap.get(channel)
      if (offsetIdx == null) return null
      const coords = fiberOffsetCache.get(fiber.id)
      if (!coords || offsetIdx >= coords.length) return null
      return coords[offsetIdx]
    }

    const getSectionCoords = (fiber: Fiber, startChannel: number, endChannel: number): [number, number][] => {
      if (fiber.coordsPrecomputed) {
        const slice = fiber.coordinates.slice(startChannel, endChannel + 1)
        return slice.filter(c => c[0] != null && c[1] != null) as [number, number][]
      }

      const idxMap = channelToOffsetIndex.get(fiber.id)
      const coords = fiberOffsetCache.get(fiber.id)
      if (!idxMap || !coords) return []

      const result: [number, number][] = []
      for (let ch = startChannel; ch <= endChannel; ch++) {
        const idx = idxMap.get(ch)
        if (idx != null && idx < coords.length) {
          result.push(coords[idx])
        }
      }
      return result
    }

    const findNearestFiberPoint = (
      lngLat: [number, number],
      maxDistDeg = 0.003,
      coverageFilter?: Map<string, CoverageRange[]>,
    ) => {
      let best: {
        fiberId: string
        direction: 0 | 1
        channel: number
        dist: number
        coord: [number, number]
      } | null = null

      for (const fiber of fibers) {
        const offsetCoords = fiberOffsetCache.get(fiber.id)
        const coords = offsetCoords ?? fiber.coordinates
        const reverseMap = offsetIndexToChannel.get(fiber.id)
        const coverageRanges = coverageFilter?.get(fiber.parentCableId)
        for (let i = 0; i < coords.length; i++) {
          const c = coords[i]
          if (c[0] == null || c[1] == null) continue
          const channel = reverseMap ? reverseMap[i] : i
          if (coverageRanges && !coverageRanges.some(r => channel >= r.start && channel <= r.end)) continue
          const ddx = (c[0] as number) - lngLat[0]
          const ddy = (c[1] as number) - lngLat[1]
          const dist = Math.sqrt(ddx * ddx + ddy * ddy)
          if (dist < maxDistDeg && (!best || dist < best.dist)) {
            best = {
              fiberId: fiber.parentCableId,
              direction: fiber.direction,
              channel,
              dist,
              coord: c as [number, number],
            }
          }
        }
      }

      if (!best) return null
      return {
        fiberId: best.fiberId,
        direction: best.direction,
        channel: best.channel,
        lng: best.coord[0],
        lat: best.coord[1],
      }
    }

    const buildCoverageRenderCacheFn = (cm: Map<string, CoverageRange[]>) => {
      const cache = new Map<string, [number, number][][]>()
      for (const fiber of fibers) {
        const ranges = cm.get(fiber.parentCableId)
        if (!ranges || ranges.length === 0) continue
        const segments: [number, number][][] = []
        for (const range of ranges) {
          const coords = getSectionCoords(fiber, range.start, range.end)
          if (coords.length >= 2) {
            segments.push(simplifyCoords(coords, SIMPLIFY_TOLERANCE))
          }
        }
        if (segments.length > 0) {
          cache.set(fiber.id, segments)
        }
      }
      return cache
    }

    return {
      fibers,
      fiberOffsetCache,
      fiberRenderCache,
      offsetIndexToChannel,
      coverageMap,
      findFiber,
      channelToCoord,
      getSectionCoords,
      findNearestFiberPoint,
      buildCoverageRenderCache: buildCoverageRenderCacheFn,
      isLoading,
    }
  }, [apiFibers, isLoading])

  return <FiberContext.Provider value={value}>{children}</FiberContext.Provider>
}

// ── Hook ─────────────────────────────────────────────────────────────────

export function useFiberData(): FiberContextType {
  const ctx = useContext(FiberContext)
  if (!ctx) throw new Error('useFiberData must be used within FiberProvider')
  return ctx
}
