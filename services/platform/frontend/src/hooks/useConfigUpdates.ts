import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRealtime } from './useRealtime'

/**
 * Subscribes to `config_updated` WebSocket channel and invalidates
 * the relevant React Query caches when configuration data changes
 * on the server.
 *
 * Currently handles infrastructure updates. Fiber geometry is statically
 * imported at build time — runtime fiber updates will require migrating
 * the frontend to fetch fibers from the API.
 *
 * Mount once near the app root (inside both RealtimeProvider and
 * QueryClientProvider).
 */
export function useConfigUpdates() {
  const { subscribe } = useRealtime()
  const queryClient = useQueryClient()

  useEffect(() => {
    return subscribe('config_updated', (data: unknown) => {
      const update = data as { type?: string }
      if (update.type === 'infrastructure') {
        queryClient.invalidateQueries({ queryKey: ['infrastructure'] })
      }
      // TODO: handle 'fibers' once frontend fetches fibers from API
      // instead of static JSON import
    })
  }, [subscribe, queryClient])
}
