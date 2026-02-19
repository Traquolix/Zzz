import { useState, useEffect, useRef } from 'react'
import { useRealtime } from './useRealtime'
import { useVehicleCounts } from './useVehicleCounts'
import { useAuth } from './useAuth'
import { parseDetections } from '@/lib/parseMessage'
import { fetchStats } from '@/api/stats'

export type TechStats = {
    // Connection
    connected: boolean

    // Server stats
    vehicleCount: number | null
    activeIncidents: number | null

    // Detection stats (computed client-side)
    totalDetections: number

    // Session info
    username: string | null
    sessionStart: number
}

export function useTechStats(): TechStats {
    const { connected, subscribe } = useRealtime()
    const { username } = useAuth()
    const { totalVehicles } = useVehicleCounts()

    const [serverStats, setServerStats] = useState<{
        vehicleCount: number | null
        activeIncidents: number | null
    }>({
        vehicleCount: null,
        activeIncidents: null,
    })

    const [totalDetections, setTotalDetections] = useState(0)
    const [sessionStart] = useState(() => Date.now())
    const detectionCountRef = useRef(0)

    // Fetch server stats periodically
    useEffect(() => {
        const loadStats = async () => {
            try {
                const data = await fetchStats()
                setServerStats({
                    vehicleCount: data.activeVehicles,
                    activeIncidents: data.activeIncidents,
                })
            } catch {
                // Silently fail - stats are optional
            }
        }

        loadStats()
        const interval = setInterval(loadStats, 5000)
        return () => clearInterval(interval)
    }, [])

    // Subscribe to detections and count them
    useEffect(() => {
        const handleDetections = (data: unknown) => {
            const detections = parseDetections(data)
            detectionCountRef.current += detections.length
            setTotalDetections(detectionCountRef.current)
        }

        return subscribe('detections', handleDetections)
    }, [subscribe])

    // Use real-time AI counts if available, fall back to server stats
    const liveCount = totalVehicles()
    const vehicleCount = liveCount > 0 ? liveCount : serverStats.vehicleCount

    return {
        connected,
        vehicleCount,
        activeIncidents: serverStats.activeIncidents,
        totalDetections,
        username,
        sessionStart,
    }
}
