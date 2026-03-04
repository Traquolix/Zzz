import { useState, useEffect, useRef, useCallback } from 'react'
import type { Incident } from '../types'

export interface IncidentToast {
    id: string
    incidentId: string
    title: string
    type: string
    severity: string
    createdAt: number
}

export function useUnseenIncidents(incidents: Incident[], loading: boolean) {
    const [unseenIds, setUnseenIds] = useState<Set<string>>(new Set())
    const [toasts, setToasts] = useState<IncidentToast[]>([])
    const prevIdsRef = useRef<Set<string>>(new Set())
    // true once loading has transitioned from true → false (REST fetch complete)
    const readyRef = useRef(false)

    useEffect(() => {
        const currentIds = new Set(incidents.map(i => i.id))

        if (!readyRef.current) {
            // Still loading or just finished — snapshot current IDs and wait
            if (!loading) readyRef.current = true
            prevIdsRef.current = currentIds
            return
        }

        const newIds: string[] = []
        for (const id of currentIds) {
            if (!prevIdsRef.current.has(id)) {
                newIds.push(id)
            }
        }

        if (newIds.length > 0) {
            setUnseenIds(prev => {
                const next = new Set(prev)
                for (const id of newIds) next.add(id)
                return next
            })

            const now = Date.now()
            const newToasts: IncidentToast[] = newIds.map(id => {
                const inc = incidents.find(i => i.id === id)!
                return {
                    id: `${id}-${now}`,
                    incidentId: id,
                    title: inc.title,
                    type: inc.type,
                    severity: inc.severity,
                    createdAt: now,
                }
            })
            setToasts(prev => [...prev, ...newToasts])
        }

        prevIdsRef.current = currentIds
    }, [incidents, loading])

    // Auto-dismiss toasts after 60s
    useEffect(() => {
        if (toasts.length === 0) return
        const timer = setInterval(() => {
            const cutoff = Date.now() - 60_000
            setToasts(prev => {
                const next = prev.filter(t => t.createdAt > cutoff)
                return next.length === prev.length ? prev : next
            })
        }, 1000)
        return () => clearInterval(timer)
    }, [toasts.length > 0])

    const markSeen = useCallback((id: string) => {
        setUnseenIds(prev => {
            if (!prev.has(id)) return prev
            const next = new Set(prev)
            next.delete(id)
            return next
        })
    }, [])

    const dismissToast = useCallback((toastId: string) => {
        setToasts(prev => prev.filter(t => t.id !== toastId))
    }, [])

    const hasUnseen = unseenIds.size > 0

    return { unseenIds, hasUnseen, markSeen, toasts, dismissToast }
}
