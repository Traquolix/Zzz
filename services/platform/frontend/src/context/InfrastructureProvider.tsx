import { useState, useEffect, type ReactNode } from 'react'
import { InfrastructureDataContext } from './InfrastructureContext'
import { useRealtime } from '@/hooks/useRealtime'
import { fetchInfrastructure } from '@/api/infrastructure'
import type { Infrastructure, FrequencyReading } from '@/types/infrastructure'
import { parseFrequencyReadings } from '@/lib/parseMessage'

/**
 * Provider for infrastructure data (bridges, tunnels).
 * Loads static data from API and subscribes to real-time frequency readings.
 */
export function InfrastructureDataProvider({ children }: { children: ReactNode }) {
    const [infrastructures, setInfrastructures] = useState<Infrastructure[]>([])
    const [latestReadings, setLatestReadings] = useState<Map<string, FrequencyReading>>(new Map())
    const [loading, setLoading] = useState(true)
    const { subscribe, connected } = useRealtime()

    // Load infrastructure on mount
    useEffect(() => {
        fetchInfrastructure()
            .then(data => {
                setInfrastructures(data)
            })
            .catch(err => console.error('Failed to fetch infrastructure:', err))
            .finally(() => setLoading(false))
    }, [])

    // Subscribe to real-time frequency readings
    useEffect(() => {
        if (!connected) return

        return subscribe('shm_readings', (data: unknown) => {
            const readings = parseFrequencyReadings(data)
            if (readings.length === 0) return
            setLatestReadings(prev => {
                const next = new Map(prev)
                for (const reading of readings) {
                    next.set(reading.infrastructureId, reading)
                }
                return next
            })
        })
    }, [connected, subscribe])

    return (
        <InfrastructureDataContext.Provider value={{ infrastructures, latestReadings, loading }}>
            {children}
        </InfrastructureDataContext.Provider>
    )
}
