import { useEffect, useState, useCallback } from 'react'
import { fetchSections, createSection, deleteSection, type ApiSection } from '@/api/sections'
import type { Section } from '../types'
import { defaultSpeedThresholds } from '../data'

/** Map an API section to the prototype Section shape. */
function toProtoSection(api: ApiSection): Section {
  return {
    id: api.id,
    fiberId: api.fiberId,
    direction: api.direction,
    name: api.name,
    startChannel: api.channelStart,
    endChannel: api.channelEnd,
    avgSpeed: 0,
    flow: 0,
    occupancy: 0,
    travelTime: 0,
    speedHistory: [],
    countHistory: [],
    speedThresholds: { ...defaultSpeedThresholds },
  }
}

export function useSections() {
  const [sections, setSections] = useState<Section[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    fetchSections()
      .then(apiSections => {
        if (mounted) {
          setSections(apiSections.map(toProtoSection))
          setLoading(false)
        }
      })
      .catch(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const addSection = useCallback(
    async (fiberId: string, direction: number, name: string, startChannel: number, endChannel: number) => {
      const api = await createSection({ fiberId, direction, name, channelStart: startChannel, channelEnd: endChannel })
      const section = toProtoSection(api)
      setSections(prev => [...prev, section])
      return section
    },
    [],
  )

  const removeSection = useCallback(async (id: string) => {
    await deleteSection(id)
    setSections(prev => prev.filter(s => s.id !== id))
  }, [])

  return { sections, loading, addSection, removeSection }
}
