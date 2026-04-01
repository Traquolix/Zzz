import { useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSections, createSection, deleteSection, renameSection, type ApiSection } from '@/api/sections'
import type { Section } from '../types'
import { defaultSpeedThresholds } from '../data'

/** Map an API section to the dashboard Section shape. */
function toDisplaySection(api: ApiSection): Section {
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
  const queryClient = useQueryClient()

  const { data: sections = [], isLoading: loading } = useQuery({
    queryKey: ['sections'],
    queryFn: async () => {
      const apiSections = await fetchSections()
      return apiSections.map(toDisplaySection)
    },
    staleTime: 60_000,
  })

  const createMutation = useMutation({
    mutationFn: (params: {
      fiberId: string
      direction: 0 | 1
      name: string
      startChannel: number
      endChannel: number
    }) =>
      createSection({
        fiberId: params.fiberId,
        direction: params.direction,
        name: params.name,
        channelStart: params.startChannel,
        channelEnd: params.endChannel,
      }),
    onSuccess: api => {
      queryClient.setQueryData<Section[]>(['sections'], prev => [...(prev ?? []), toDisplaySection(api)])
    },
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameSection(id, name),
    onSuccess: result => {
      queryClient.setQueryData<Section[]>(['sections'], prev =>
        (prev ?? []).map(s => (s.id === result.id ? { ...s, name: result.name } : s)),
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSection,
    onSuccess: (_data, id) => {
      queryClient.setQueryData<Section[]>(['sections'], prev => (prev ?? []).filter(s => s.id !== id))
    },
  })

  const addSection = useCallback(
    async (fiberId: string, direction: 0 | 1, name: string, startChannel: number, endChannel: number) => {
      const api = await createMutation.mutateAsync({ fiberId, direction, name, startChannel, endChannel })
      return toDisplaySection(api)
    },
    [createMutation],
  )

  const removeSection = useCallback(
    async (id: string) => {
      await deleteMutation.mutateAsync(id)
    },
    [deleteMutation],
  )

  const updateSectionName = useCallback(
    async (id: string, name: string) => {
      await renameMutation.mutateAsync({ id, name })
    },
    [renameMutation],
  )

  return { sections, loading, addSection, removeSection, updateSectionName }
}
