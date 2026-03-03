import { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { parseDetections } from '@/lib/parseMessage'
import { useFibers } from '@/hooks/useFibers'
import type { SelectedLandmark } from '@/types/selection'
import type { LandmarkData, SectionDataPoint, LandmarkInfo } from './types'
import { TIME_WINDOW_MS, CHANNEL_TOLERANCE, MAX_LANDMARK_POINTS, MAX_SECTION_HISTORY } from './types'
import { CircularBuffer } from '@/lib/CircularBuffer'
import { groupDetectionsIntoVehiclePasses } from '@/lib/groupDetections'

/** Internal storage using CircularBuffer instead of plain arrays. */
type LandmarkBuffer = {
    fiberId: string
    channel: number
    name: string
    buffer: CircularBuffer<{ timestamp: number; speed: number; count: number; direction: 0 | 1 }>
}

interface UseTrafficDataProps {
    landmarksMap: Map<string, { name: string; favorite: boolean }>
    selectedLandmark: SelectedLandmark | null
    sectionsArray: { id: string; fiberId: string; startChannel: number; endChannel: number }[]
}

export function useTrafficData({ landmarksMap, selectedLandmark, sectionsArray }: UseTrafficDataProps) {
    const { fibers } = useFibers()
    const { subscribe } = useRealtime()
    const [landmarkData, setLandmarkData] = useState<Map<string, LandmarkData>>(new Map())
    const [sectionData, setSectionData] = useState<Map<string, SectionDataPoint[]>>(new Map())
    const [now, setNow] = useState(() => Date.now())

    // Ring buffers stored in refs to avoid re-creating on every render
    const landmarkBuffers = useRef<Map<string, LandmarkBuffer>>(new Map())
    const sectionBuffers = useRef<Map<string, CircularBuffer<SectionDataPoint>>>(new Map())

    // Parse landmarks from landmarksMap with coordinates
    const landmarks = useMemo((): LandmarkInfo[] => {
        const result: LandmarkInfo[] = []
        landmarksMap.forEach((entry, key) => {
            const lastColonIdx = key.lastIndexOf(':')
            if (lastColonIdx === -1) return

            const fiberId = key.slice(0, lastColonIdx)
            const channel = parseInt(key.slice(lastColonIdx + 1), 10)

            if (fiberId && !isNaN(channel)) {
                const fiber = fibers.find(f => f.id === fiberId)
                const coords = fiber?.coordinates[channel]
                if (coords) {
                    result.push({
                        fiberId,
                        channel,
                        name: entry.name,
                        key,
                        lng: coords[0],
                        lat: coords[1],
                        favorite: entry.favorite
                    })
                }
            }
        })
        return result
    }, [landmarksMap, fibers])

    // Build list of tracked landmarks
    const trackedLandmarks = useMemo(() => {
        const result = [...landmarks]

        if (selectedLandmark) {
            const selectedKey = `${selectedLandmark.fiberId}:${selectedLandmark.channel}`
            const alreadyTracked = result.some(l => l.key === selectedKey)
            if (!alreadyTracked) {
                result.push({
                    fiberId: selectedLandmark.fiberId,
                    channel: selectedLandmark.channel,
                    name: `Channel ${selectedLandmark.channel}`,
                    key: selectedKey,
                    lng: selectedLandmark.lng,
                    lat: selectedLandmark.lat,
                    favorite: false
                })
            }
        }

        return result
    }, [landmarks, selectedLandmark])

    // Update time every second
    useEffect(() => {
        const interval = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(interval)
    }, [])

    // Flush buffers to state (called after processing detections)
    const flushLandmarks = useCallback(() => {
        const next = new Map<string, LandmarkData>()
        landmarkBuffers.current.forEach((lb, key) => {
            next.set(key, {
                fiberId: lb.fiberId,
                channel: lb.channel,
                name: lb.name,
                points: lb.buffer.toArray()
            })
        })
        setLandmarkData(next)
    }, [])

    const flushSections = useCallback(() => {
        const next = new Map<string, SectionDataPoint[]>()
        sectionBuffers.current.forEach((buf, key) => {
            next.set(key, buf.toArray())
        })
        setSectionData(next)
    }, [])

    // Subscribe to detections
    useEffect(() => {
        if (trackedLandmarks.length === 0 && sectionsArray.length === 0) return

        return subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            if (detections.length === 0) return

            const cutoffTime = Date.now() - TIME_WINDOW_MS
            let landmarksChanged = false
            let sectionsChanged = false

            // Process landmark data
            if (trackedLandmarks.length > 0) {
                trackedLandmarks.forEach(landmark => {
                    const relevant = detections.filter(d =>
                        d.fiberLine === landmark.fiberId &&
                        Math.abs(d.channel - landmark.channel) <= CHANNEL_TOLERANCE
                    )

                    if (relevant.length > 0) {
                        let lb = landmarkBuffers.current.get(landmark.key)
                        if (!lb) {
                            lb = {
                                fiberId: landmark.fiberId,
                                channel: landmark.channel,
                                name: landmark.name,
                                buffer: new CircularBuffer(MAX_LANDMARK_POINTS)
                            }
                            landmarkBuffers.current.set(landmark.key, lb)
                        }

                        // Evict stale data
                        lb.buffer.drain(cutoffTime, p => p.timestamp)

                        // Push new detections
                        const newPoints = relevant.map(d => ({
                            timestamp: d.timestamp,
                            speed: d.speed,
                            count: d.count,
                            direction: d.direction
                        }))
                        lb.buffer.pushMany(newPoints)
                        landmarksChanged = true
                    }
                })

                if (landmarksChanged) flushLandmarks()
            }

            // Process section data
            if (sectionsArray.length > 0) {
                const timestamp = Date.now()

                sectionsArray.forEach(section => {
                    const sectionDetections = detections.filter(d =>
                        d.fiberLine === section.fiberId &&
                        d.channel >= section.startChannel &&
                        d.channel <= section.endChannel
                    )

                    let speed0Sum = 0, count0 = 0
                    let speed1Sum = 0, count1 = 0

                    sectionDetections.forEach(d => {
                        if (d.direction === 0) {
                            speed0Sum += d.speed * d.count
                            count0 += d.count
                        } else {
                            speed1Sum += d.speed * d.count
                            count1 += d.count
                        }
                    })

                    if (count0 > 0 || count1 > 0) {
                        let buf = sectionBuffers.current.get(section.id)
                        if (!buf) {
                            buf = new CircularBuffer<SectionDataPoint>(MAX_SECTION_HISTORY)
                            sectionBuffers.current.set(section.id, buf)
                        }

                        // Evict stale data
                        buf.drain(cutoffTime, p => p.timestamp)

                        buf.push({
                            timestamp,
                            speed0: count0 > 0 ? speed0Sum / count0 : null,
                            speed1: count1 > 0 ? speed1Sum / count1 : null,
                            count0,
                            count1
                        })
                        sectionsChanged = true
                    }
                })

                if (sectionsChanged) flushSections()
            }
        })
    }, [trackedLandmarks, sectionsArray, subscribe, flushLandmarks, flushSections])

    // Get visible points for selected landmark
    const visiblePoints = useMemo(() => {
        if (!selectedLandmark) return []
        const key = `${selectedLandmark.fiberId}:${selectedLandmark.channel}`
        const data = landmarkData.get(key)
        if (!data) return []

        const minTime = now - TIME_WINDOW_MS
        const timeFiltered = data.points.filter(p => p.timestamp > minTime)
        return groupDetectionsIntoVehiclePasses(timeFiltered)
    }, [selectedLandmark, landmarkData, now])

    return {
        landmarks,
        landmarkData,
        sectionData,
        visiblePoints,
        now
    }
}
