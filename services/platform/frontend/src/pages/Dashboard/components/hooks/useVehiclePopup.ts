import { useRef, useCallback, useMemo } from 'react'
import mapboxgl from 'mapbox-gl'
import { getSpeedColor } from '../../data'
import type { Fiber, SpeedThresholds } from '../../types'
import type { VehiclePosition } from '../../hooks/useVehicleSim'
import i18n from '@/i18n'

interface UseVehiclePopupParams {
  mapRef: React.RefObject<mapboxgl.Map | null>
  thresholdLookupRef: React.RefObject<
    ((cableId: string, direction: 0 | 1, channel: number) => SpeedThresholds) | undefined
  >
  findFiberRef: React.RefObject<(cableId: string, direction: number) => Fiber | undefined>
}

export function useVehiclePopup({ mapRef, thresholdLookupRef, findFiberRef }: UseVehiclePopupParams) {
  const selectedVehicleIdRef = useRef<string | null>(null)
  const popupRef = useRef<mapboxgl.Popup | null>(null)

  const getPopup = useCallback(() => {
    if (!popupRef.current) {
      popupRef.current = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        className: 'dash-vehicle-popup',
        maxWidth: '220px',
        offset: [0, -12],
      })
    }
    return popupRef.current
  }, [])

  const dismiss = useCallback(() => {
    selectedVehicleIdRef.current = null
    popupRef.current?.remove()
  }, [])

  const select = useCallback((vehicleId: string) => {
    selectedVehicleIdRef.current = vehicleId
  }, [])

  const update = useCallback(
    (positions: VehiclePosition[]) => {
      const selectedId = selectedVehicleIdRef.current
      if (!selectedId) return
      const map = mapRef.current
      if (!map) return
      const v = positions.find(p => p.id === selectedId)
      if (!v || v.opacity < 0.05) {
        dismiss()
        return
      }
      const fiber = findFiberRef.current(v.fiberId, v.direction)
      const fiberName = fiber?.name ?? v.fiberId
      const dir = v.direction === 0 ? '\u2192' : '\u2190'
      const lookup = thresholdLookupRef.current
      const thresholds = lookup?.(v.fiberId, v.direction, v.channel)
      const speedColor = getSpeedColor(v.detectionSpeed, thresholds)
      const vehicleLabel =
        v.carCount > 1 ? `${v.carCount} ${i18n.t('common.vehicles')}` : `1 ${i18n.t('common.vehicles')}`
      const popup = getPopup()
      popup
        .setLngLat([v.position[0], v.position[1]])
        .setHTML(
          `<div class="dash-vehicle-popup-body">` +
            `<div class="dash-vehicle-popup-speed" style="color:${speedColor}">${Math.round(v.detectionSpeed)} ${i18n.t('common.speedUnit')}</div>` +
            `<div class="dash-vehicle-popup-detail">${fiberName} ${dir} \u00b7 ch ${v.channel}</div>` +
            `<div class="dash-vehicle-popup-detail">${vehicleLabel}</div>` +
            `</div>`,
        )
      if (!popup.isOpen()) popup.addTo(map)
    },
    [mapRef, thresholdLookupRef, dismiss, getPopup, findFiberRef],
  )

  const isSelected = useCallback((vehicleId: string) => selectedVehicleIdRef.current === vehicleId, [])

  const cleanup = useCallback(() => {
    popupRef.current?.remove()
    popupRef.current = null
    selectedVehicleIdRef.current = null
  }, [])

  return useMemo(
    () => ({ dismiss, select, update, isSelected, selectedVehicleIdRef, cleanup }),
    [dismiss, select, update, isSelected, cleanup],
  )
}
