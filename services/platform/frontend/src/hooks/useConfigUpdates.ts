import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRealtime } from './useRealtime'

/**
 * Subscribes to `config_updated` WebSocket channel and invalidates
 * the relevant React Query caches when configuration data changes
 * on the server.
 *
 * Handles infrastructure and fiber updates. Mount once near the app root
 * (inside both RealtimeProvider and QueryClientProvider).
 */
export function useConfigUpdates() {
  const { subscribe } = useRealtime()
  const queryClient = useQueryClient()

  useEffect(() => {
    return subscribe('config_updated', (data: unknown) => {
      const update = data as { type?: string }
      if (update.type === 'infrastructure') {
        queryClient.invalidateQueries({ queryKey: ['infrastructure'] })
      } else if (update.type === 'fibers') {
        queryClient.invalidateQueries({ queryKey: ['fibers'] })
      }
    })
  }, [subscribe, queryClient])
}
