import { useState, useEffect, useRef, useCallback } from 'react'
import type { DisplayIncident } from '../types'

export interface IncidentToast {
  id: string
  incidentId: string
  title: string
  type: string
  severity: string
  createdAt: number
}

export function useUnseenIncidents(incidents: DisplayIncident[], loading: boolean) {
  const [unseenIds, setUnseenIds] = useState<Set<string>>(new Set())
  const [toasts, setToasts] = useState<IncidentToast[]>([])
  const prevIdsRef = useRef<Set<string>>(new Set())
  // true once loading has transitioned from true → false (REST fetch complete)
  const readyRef = useRef(false)

  useEffect(() => {
    // When loading restarts (e.g. flow switch), clear stale toasts/unseen
    // and re-arm the loading guard so the new flow's initial incidents
    // aren't treated as "new".
    if (loading) {
      if (readyRef.current) {
        setUnseenIds(new Set())
        setToasts([])
        prevIdsRef.current = new Set()
        readyRef.current = false
      }
      return
    }

    const currentIds = new Set(incidents.map(i => i.id))

    if (!readyRef.current) {
      // Just finished loading — snapshot current IDs and wait
      readyRef.current = true
      prevIdsRef.current = currentIds
      return
    }

    const newIds: string[] = []
    for (const id of currentIds) {
      if (!prevIdsRef.current.has(id)) {
        newIds.push(id)
      }
    }

    // Auto-mark resolved incidents as seen — nothing to act on
    setUnseenIds(prev => {
      let changed = false
      const next = new Set(prev)
      for (const id of prev) {
        const inc = incidents.find(i => i.id === id)
        if (inc?.resolved) {
          next.delete(id)
          changed = true
        }
      }
      return changed ? next : prev
    })

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

  // Auto-dismiss toasts after 10s
  const hasToasts = toasts.length > 0
  useEffect(() => {
    if (!hasToasts) return
    const timer = setInterval(() => {
      const cutoff = Date.now() - 10_000
      setToasts(prev => {
        const next = prev.filter(t => t.createdAt > cutoff)
        return next.length === prev.length ? prev : next
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [hasToasts])

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

  const markAllSeen = useCallback(() => {
    setUnseenIds(new Set())
    setToasts([])
  }, [])

  const hasUnseen = unseenIds.size > 0

  return { unseenIds, hasUnseen, markSeen, markAllSeen, toasts, dismissToast }
}
