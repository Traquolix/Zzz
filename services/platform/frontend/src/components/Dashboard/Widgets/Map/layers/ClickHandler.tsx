import { useEffect, useRef, useMemo } from 'react'
import { useMap } from '../MapContext'
import { useFibers } from '@/hooks/useFibers'
import { useLandmarkSelection } from '@/hooks/useLandmarkSelection'
import { useVehicleSelection } from '@/hooks/useVehicleSelection'
import { useSection } from '@/hooks/useSection'
import { useMapSelection } from '@/hooks/useMapSelection'
import { useIncidents } from '@/hooks/useIncidents'
import { getFiberOffsetCoords } from '@/lib/geoUtils'

const VEHICLE_THRESHOLD = 0.00005
const LANDMARK_THRESHOLD = 0.0003
const INCIDENT_THRESHOLD = 0.0003

export function ClickHandler() {
    const map = useMap()
    const { fibers, getPosition } = useFibers()
    const { selectLandmark } = useLandmarkSelection()
    const { selectedVehicle, vehiclePositions, selectVehicle } = useVehicleSelection()
    const { pendingPoint, setPendingPoint, openNamingDialog, sectionCreationMode, setSectionCreationMode } = useSection()
    const { select, selectIncident } = useMapSelection()
    const { incidents } = useIncidents()

    // Precompute offset coordinates per fiber for click distance calculations
    const fiberOffsetCoords = useMemo(() => {
        const map = new Map<string, [number, number][]>()
        for (const fiber of fibers) {
            map.set(fiber.id, getFiberOffsetCoords(fiber))
        }
        return map
    }, [fibers])

    // Use refs for high-frequency data to avoid re-registering the click handler at 10Hz
    const vehiclePositionsRef = useRef(vehiclePositions)
    useEffect(() => { vehiclePositionsRef.current = vehiclePositions }, [vehiclePositions])

    const selectedVehicleRef = useRef(selectedVehicle)
    useEffect(() => { selectedVehicleRef.current = selectedVehicle }, [selectedVehicle])

    useEffect(() => {
        if (!map) return

        const handleClick = (e: mapboxgl.MapMouseEvent) => {
            const { lng, lat } = e.lngLat
            const isCtrlClick = e.originalEvent.ctrlKey || e.originalEvent.metaKey

            // Find nearest point on any fiber's offset line
            let nearestLandmark = null
            let landmarkDist = Infinity
            for (const fiber of fibers) {
                const coords = fiberOffsetCoords.get(fiber.id)
                if (!coords) continue
                for (let ch = 0; ch < coords.length; ch++) {
                    const coord = coords[ch]
                    if (coord[0] == null || coord[1] == null) continue
                    const d = Math.hypot(coord[0] - lng, coord[1] - lat)
                    if (d < landmarkDist) {
                        landmarkDist = d
                        nearestLandmark = { fiberId: fiber.id, channel: ch, lng: coord[0], lat: coord[1] }
                    }
                }
            }

            // Handle Ctrl+Click or sectionCreationMode for starting section creation
            if ((isCtrlClick || sectionCreationMode) && !pendingPoint) {
                if (!nearestLandmark || landmarkDist >= LANDMARK_THRESHOLD) return
                // First click - set start point and deselect everything
                select({ type: 'none' })
                setPendingPoint(nearestLandmark)
                // Exit creation mode after first click (user now has pending point)
                if (sectionCreationMode) setSectionCreationMode(false)
                return // Don't process as regular click
            }

            // If we have a pending point, any click (regular or Ctrl) completes the section
            if (pendingPoint) {
                if (!nearestLandmark || landmarkDist >= LANDMARK_THRESHOLD) {
                    // Click too far from fiber - cancel
                    setPendingPoint(null)
                    return
                }

                if (nearestLandmark.fiberId !== pendingPoint.fiberId) {
                    // Different fiber - cancel and start fresh if Ctrl held
                    if (isCtrlClick) {
                        setPendingPoint(nearestLandmark)
                    } else {
                        setPendingPoint(null)
                    }
                    return
                }

                // Same fiber - create section
                const startChannel = Math.min(pendingPoint.channel, nearestLandmark.channel)
                const endChannel = Math.max(pendingPoint.channel, nearestLandmark.channel)

                // Clear pending point and open naming dialog
                setPendingPoint(null)
                openNamingDialog(nearestLandmark.fiberId, startChannel, endChannel)
                return
            }

            // Find nearest vehicle
            let nearestVehicle = null
            let vehicleDist = Infinity
            for (const v of vehiclePositionsRef.current) {
                if (v.isDetectionMarker) continue
                const d = Math.hypot(v.position[0] - lng, v.position[1] - lat)
                if (d < vehicleDist && d < VEHICLE_THRESHOLD) {
                    vehicleDist = d
                    nearestVehicle = v
                }
            }

            // Find nearest incident
            let nearestIncident = null
            let incidentDist = Infinity
            for (const incident of incidents) {
                if (incident.status !== 'active') continue
                const pos = getPosition(incident.fiberLine, incident.channel, 0)
                if (!pos) continue
                const d = Math.hypot(pos.lng - lng, pos.lat - lat)
                if (d < incidentDist && d < INCIDENT_THRESHOLD) {
                    incidentDist = d
                    nearestIncident = { ...incident, lng: pos.lng, lat: pos.lat }
                }
            }

            // Select based on what was clicked (unified selection auto-deselects others)
            // Priority: vehicle > incident > landmark
            if (nearestVehicle) {
                const pt = map.project([nearestVehicle.position[0], nearestVehicle.position[1]])
                selectVehicle({
                    id: nearestVehicle.id,
                    speed: nearestVehicle.speed,
                    detectionSpeed: nearestVehicle.detectionSpeed,
                    channel: nearestVehicle.channel,
                    direction: nearestVehicle.direction,
                    screenX: pt.x,
                    screenY: pt.y
                })
            } else if (selectedVehicleRef.current) {
                // Click away from vehicle - deselect
                selectVehicle(null)
            } else if (nearestIncident) {
                selectIncident({
                    id: nearestIncident.id,
                    type: nearestIncident.type,
                    severity: nearestIncident.severity,
                    fiberLine: nearestIncident.fiberLine,
                    channel: nearestIncident.channel,
                    lng: nearestIncident.lng,
                    lat: nearestIncident.lat
                })
            } else if (nearestLandmark && landmarkDist < LANDMARK_THRESHOLD) {
                selectLandmark(nearestLandmark)
            } else {
                // Click away - deselect everything
                select({ type: 'none' })
            }
        }

        map.on('click', handleClick)
        return () => { map.off('click', handleClick) }
    }, [map, fibers, fiberOffsetCoords, selectLandmark, selectVehicle, pendingPoint, setPendingPoint, openNamingDialog, select, sectionCreationMode, setSectionCreationMode, incidents, getPosition, selectIncident])

    return null
}
