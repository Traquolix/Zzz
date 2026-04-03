import { useCallback } from 'react'
import { useFiberData } from '../context/FiberContext'
import type { Incident as ApiIncident } from '@/types/incident'
import type { DisplayIncident } from '../types'

/**
 * Enriches an API incident with display fields computed from fiber geometry.
 *
 * Accesses FiberContext directly so callers don't need to thread
 * findFiber / channelToCoord through props.
 */
export function useDisplayIncident() {
  const { findFiber, channelToCoord } = useFiberData()

  const toDisplayIncident = useCallback(
    (api: ApiIncident): DisplayIncident => {
      const fiber = findFiber(api.fiberId, api.direction)
      const loc = fiber ? channelToCoord(fiber, api.channel) : null
      const fiberName = fiber?.name ?? api.fiberId
      const typeLabel = api.type.charAt(0).toUpperCase() + api.type.slice(1)
      const title = `${typeLabel} \u2014 ${fiberName}`

      let description = `${typeLabel} detected on ${fiberName} at channel ${api.channel}.`
      if (api.speedBefore != null && api.speedDuring != null) {
        description += ` Speed dropped from ${Math.round(api.speedBefore)} to ${Math.round(api.speedDuring)} km/h.`
      }

      return {
        ...api,
        title,
        description,
        location: loc ?? [7.24, 43.72],
        resolved: api.status !== 'active',
      }
    },
    [findFiber, channelToCoord],
  )

  return toDisplayIncident
}
