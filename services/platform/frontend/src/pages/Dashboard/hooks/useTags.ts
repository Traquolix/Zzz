import { useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchTags, createTag, updateTag, deleteTag } from '@/api/tags'
import type { IncidentTag } from '@/types/incident'

export function useTags() {
  const queryClient = useQueryClient()

  const { data: tags = [], isLoading: loading } = useQuery({
    queryKey: ['tags'],
    queryFn: fetchTags,
    staleTime: 60_000,
  })

  const createMutation = useMutation({
    mutationFn: ({ name, color }: { name: string; color: string }) => createTag(name, color),
    onSuccess: tag => {
      queryClient.setQueryData<IncidentTag[]>(['tags'], prev => [...(prev ?? []), tag])
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; color?: string } }) => updateTag(id, data),
    onSuccess: updated => {
      queryClient.setQueryData<IncidentTag[]>(['tags'], prev =>
        (prev ?? []).map(t => (t.id === updated.id ? updated : t)),
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteTag,
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: ['tags'] })
      const previous = queryClient.getQueryData<IncidentTag[]>(['tags'])
      queryClient.setQueryData<IncidentTag[]>(['tags'], prev => (prev ?? []).filter(t => t.id !== id))
      return { previous }
    },
    onError: (_err, _id, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['tags'], context.previous)
      }
    },
  })

  const addTag = useCallback(
    async (name: string, color: string) => {
      await createMutation.mutateAsync({ name, color })
    },
    [createMutation],
  )

  const editTag = useCallback(
    async (id: string, data: { name?: string; color?: string }) => {
      await updateMutation.mutateAsync({ id, data })
    },
    [updateMutation],
  )

  const removeTag = useCallback(
    async (id: string) => {
      await deleteMutation.mutateAsync(id)
    },
    [deleteMutation],
  )

  return { tags, loading, addTag, editTag, removeTag }
}

export function useTagColor() {
  const { tags } = useTags()
  return useMemo(() => {
    const m = new Map(tags.map(t => [t.name, t.color]))
    return (name: string) => m.get(name) ?? '#6b7280'
  }, [tags])
}
