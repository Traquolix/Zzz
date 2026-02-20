import { useEffect, useState, useMemo, useCallback } from 'react'
import { useRealtime } from '@/hooks/useRealtime'
import { parseDetections } from '@/lib/parseMessage'
import { useLandmarkSelection } from '@/hooks/useLandmarkSelection'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'
import { useSectionStats } from '@/hooks/useSectionStats'
import { useMapInstance } from '@/hooks/useMapInstance'
import { useDashboardState } from '@/context/DashboardContext'
import { LandmarkList } from './LandmarkList'
import { LandmarkDetail } from './LandmarkDetail'
import { SectionList } from './SectionList'
import { SectionDetail } from './SectionDetail'
import type { LandmarkData, SectionDataPoint, LandmarkInfo } from './types'
import { TIME_WINDOW_MS, CHANNEL_TOLERANCE } from './types'
import { groupDetectionsIntoVehiclePasses } from '@/lib/groupDetections'

export function TrafficMonitorWidget() {
    const {
        selectedLandmark,
        selectLandmark,
        landmarks: landmarksMap,
        getLandmarkName,
        renameLandmark,
        toggleLandmarkFavorite,
        deleteLandmark
    } = useLandmarkSelection()
    const { fibers } = useFibers()
    const { subscribe } = useRealtime()
    const { sections, selectSection, selectedSection, renameSection, deleteSection, toggleSectionFavorite } = useSection()
    const { stats: sectionStats } = useSectionStats(sections)
    const { flyToWithLayer, fitBoundsWithLayer, ensureLayerVisible } = useMapInstance()
    const { widgetStates, setTrafficMonitorTab } = useDashboardState()

    const activeTab = widgetStates.trafficMonitorTab
    const [landmarkData, setLandmarkData] = useState<Map<string, LandmarkData>>(new Map())
    const [sectionData, setSectionData] = useState<Map<string, SectionDataPoint[]>>(new Map())
    const [now, setNow] = useState(() => Date.now())

    // Parse landmarks from landmarksMap with coordinates
    // Key format is "fiberId:channel" where fiberId can contain ":" (e.g., "carros:0:150")
    const landmarks = useMemo((): LandmarkInfo[] => {
        const result: LandmarkInfo[] = []
        landmarksMap.forEach((entry, key) => {
            // Split from the end to handle fiberId containing ":"
            const lastColonIdx = key.lastIndexOf(':')
            if (lastColonIdx === -1) return

            const fiberId = key.slice(0, lastColonIdx)
            const channel = parseInt(key.slice(lastColonIdx + 1), 10)

            if (fiberId && !isNaN(channel)) {
                const fiber = fibers.find(f => f.id === fiberId)
                const coords = fiber?.coordinates[channel]
                if (coords) {
                    result.push({
                        fiberId,
                        channel,
                        name: entry.name,
                        key,
                        lng: coords[0],
                        lat: coords[1],
                        favorite: entry.favorite
                    })
                }
            }
        })
        return result
    }, [landmarksMap, fibers])

    // Convert sections Map to array
    const sectionsArray = useMemo(() => {
        return Array.from(sections.values())
    }, [sections])

    // Update time every second
    useEffect(() => {
        const interval = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(interval)
    }, [])

    // Build list of all landmarks to track (saved + currently selected if not saved)
    const trackedLandmarks = useMemo(() => {
        const result = [...landmarks]

        if (selectedLandmark) {
            const selectedKey = `${selectedLandmark.fiberId}:${selectedLandmark.channel}`
            const alreadyTracked = result.some(l => l.key === selectedKey)
            if (!alreadyTracked) {
                result.push({
                    fiberId: selectedLandmark.fiberId,
                    channel: selectedLandmark.channel,
                    name: `Channel ${selectedLandmark.channel}`,
                    key: selectedKey,
                    lng: selectedLandmark.lng,
                    lat: selectedLandmark.lat,
                    favorite: false
                })
            }
        }

        return result
    }, [landmarks, selectedLandmark])

    // Subscribe to detections for landmarks and sections (single subscription)
    useEffect(() => {
        if (trackedLandmarks.length === 0 && sectionsArray.length === 0) return

        return subscribe('detections', (data: unknown) => {
            const detections = parseDetections(data)
            if (detections.length === 0) return

            // Process landmark data
            if (trackedLandmarks.length > 0) {
                setLandmarkData(prev => {
                    const next = new Map(prev)

                    trackedLandmarks.forEach(landmark => {
                        // Detection fiberLine is parent (e.g., "mathis"), landmark.fiberId is directional (e.g., "mathis:0")
                        const relevant = detections.filter(d => {
                            const directionalId = `${d.fiberLine}:${d.direction}`
                            return directionalId === landmark.fiberId &&
                                Math.abs(d.channel - landmark.channel) <= CHANNEL_TOLERANCE
                        })

                        if (relevant.length > 0) {
                            const existing = next.get(landmark.key) || {
                                fiberId: landmark.fiberId,
                                channel: landmark.channel,
                                name: landmark.name,
                                points: []
                            }

                            const newPoints = relevant.map(d => ({
                                timestamp: d.timestamp,
                                speed: d.speed,
                                count: d.count,
                                direction: d.direction
                            }))

                            const cutoffTime = Date.now() - TIME_WINDOW_MS
                            const allPoints = [...existing.points, ...newPoints].filter(p => p.timestamp > cutoffTime)

                            next.set(landmark.key, {
                                ...existing,
                                points: allPoints
                            })
                        }
                    })

                    return next
                })
            }

            // Process section data
            if (sectionsArray.length > 0) {
                const timestamp = Date.now()
                const cutoffTime = timestamp - TIME_WINDOW_MS

                setSectionData(prev => {
                    const next = new Map(prev)

                    sectionsArray.forEach(section => {
                        // Detection fiberLine is parent (e.g., "mathis"), section.fiberId is directional (e.g., "mathis:0")
                        const sectionDetections = detections.filter(d => {
                            const directionalId = `${d.fiberLine}:${d.direction}`
                            return directionalId === section.fiberId &&
                                d.channel >= section.startChannel &&
                                d.channel <= section.endChannel
                        })

                        let speed0Sum = 0, count0 = 0
                        let speed1Sum = 0, count1 = 0

                        sectionDetections.forEach(d => {
                            if (d.direction === 0) {
                                speed0Sum += d.speed * d.count
                                count0 += d.count
                            } else {
                                speed1Sum += d.speed * d.count
                                count1 += d.count
                            }
                        })

                        const newPoint: SectionDataPoint = {
                            timestamp,
                            speed0: count0 > 0 ? speed0Sum / count0 : null,
                            speed1: count1 > 0 ? speed1Sum / count1 : null,
                            count0,
                            count1
                        }

                        if (count0 > 0 || count1 > 0) {
                            const existing = next.get(section.id) || []
                            const filtered = existing.filter(p => p.timestamp > cutoffTime)
                            next.set(section.id, [...filtered, newPoint])
                        }
                    })

                    return next
                })
            }
        })
    }, [trackedLandmarks, sectionsArray, subscribe])

    // Get visible points for selected landmark
    const visiblePoints = useMemo(() => {
        if (!selectedLandmark) return []
        const key = `${selectedLandmark.fiberId}:${selectedLandmark.channel}`
        const data = landmarkData.get(key)
        if (!data) return []

        const minTime = now - TIME_WINDOW_MS
        const timeFiltered = data.points.filter(p => p.timestamp > minTime)
        return groupDetectionsIntoVehiclePasses(timeFiltered)
    }, [selectedLandmark, landmarkData, now])

    // Handlers
    const handleLandmarkSelect = useCallback((landmark: LandmarkInfo) => {
        ensureLayerVisible('landmarks')
        selectLandmark({
            fiberId: landmark.fiberId,
            channel: landmark.channel,
            lng: landmark.lng,
            lat: landmark.lat
        })
    }, [ensureLayerVisible, selectLandmark])

    const handleLandmarkFlyTo = useCallback((landmark: LandmarkInfo, e: React.MouseEvent) => {
        e.stopPropagation()
        flyToWithLayer(landmark.lng, landmark.lat, 'landmarks', 16, 3000)
    }, [flyToWithLayer])

    const handleSectionSelect = useCallback((sectionId: string, fiberId: string) => {
        ensureLayerVisible('sections')
        selectSection({ sectionId, fiberId })
    }, [ensureLayerVisible, selectSection])

    const handleSectionFlyTo = useCallback((sectionId: string, e: React.MouseEvent) => {
        e.stopPropagation()
        const section = sections.get(sectionId)
        if (section) {
            const fiber = fibers.find(f => f.id === section.fiberId)
            if (fiber) {
                const startCoord = fiber.coordinates[section.startChannel]
                const endCoord = fiber.coordinates[section.endChannel]
                if (startCoord && endCoord) {
                    fitBoundsWithLayer([startCoord, endCoord], 'sections', 80, 3000)
                }
            }
        }
    }, [sections, fibers, fitBoundsWithLayer])

    const handleSelectedLandmarkRename = useCallback((name: string) => {
        if (selectedLandmark) {
            renameLandmark(selectedLandmark.fiberId, selectedLandmark.channel, name)
        }
    }, [selectedLandmark, renameLandmark])

    const handleSelectedLandmarkFlyTo = useCallback((lng: number, lat: number) => {
        flyToWithLayer(lng, lat, 'landmarks', 16, 3000)
    }, [flyToWithLayer])

    const hasLandmarks = landmarks.length > 0
    const hasSections = sectionsArray.length > 0
    const showLandmarkEmptyState = !hasLandmarks && !selectedLandmark
    const showEmptyState = (activeTab === 'landmarks' && showLandmarkEmptyState) || (activeTab === 'sections' && !hasSections)

    const selectedKey = selectedLandmark ? `${selectedLandmark.fiberId}:${selectedLandmark.channel}` : null
    const selectedName = selectedLandmark ? getLandmarkName(selectedLandmark.fiberId, selectedLandmark.channel) : null

    return (
        <div className="h-full flex flex-col bg-white overflow-hidden">
            {/* Tabs */}
            <div className="flex-shrink-0 flex border-b border-slate-200 bg-slate-50">
                <button
                    onClick={() => setTrafficMonitorTab('landmarks')}
                    className={`flex-1 px-4 py-2 text-xs font-medium transition-colors relative ${
                        activeTab === 'landmarks'
                            ? 'text-blue-600 bg-white'
                            : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                    }`}
                >
                    <div className="flex items-center justify-center gap-1.5">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                        </svg>
                        Landmarks
                        {hasLandmarks && (
                            <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                                activeTab === 'landmarks' ? 'bg-blue-100 text-blue-600' : 'bg-slate-200 text-slate-500'
                            }`}>
                                {landmarks.length}
                            </span>
                        )}
                    </div>
                    {activeTab === 'landmarks' && (
                        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />
                    )}
                </button>
                <button
                    onClick={() => setTrafficMonitorTab('sections')}
                    className={`flex-1 px-4 py-2 text-xs font-medium transition-colors relative ${
                        activeTab === 'sections'
                            ? 'text-blue-600 bg-white'
                            : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                    }`}
                >
                    <div className="flex items-center justify-center gap-1.5">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                        </svg>
                        Sections
                        {hasSections && (
                            <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                                activeTab === 'sections' ? 'bg-blue-100 text-blue-600' : 'bg-slate-200 text-slate-500'
                            }`}>
                                {sectionsArray.length}
                            </span>
                        )}
                    </div>
                    {activeTab === 'sections' && (
                        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />
                    )}
                </button>
            </div>

            {/* Empty state */}
            {showEmptyState && (
                <div className="flex-1 flex items-center justify-center text-slate-400 text-sm bg-gradient-to-b from-slate-50 to-white">
                    <div className="text-center px-4">
                        {activeTab === 'landmarks' ? (
                            <>
                                <svg className="w-10 h-10 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                <div className="font-medium text-slate-500 mb-1">No landmarks</div>
                                <div className="text-xs text-slate-400">Double-click on a fiber to create one</div>
                            </>
                        ) : (
                            <>
                                <svg className="w-10 h-10 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                                </svg>
                                <div className="font-medium text-slate-500 mb-1">No sections</div>
                                <div className="text-xs text-slate-400">Use Ctrl+Click on a fiber to define a section</div>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Landmarks tab content */}
            {activeTab === 'landmarks' && (hasLandmarks || selectedLandmark) && (
                <>
                    <LandmarkList
                        landmarks={landmarks}
                        fibers={fibers}
                        landmarkData={landmarkData}
                        selectedKey={selectedKey}
                        now={now}
                        onSelect={handleLandmarkSelect}
                        onFlyTo={handleLandmarkFlyTo}
                        onRename={renameLandmark}
                        onToggleFavorite={toggleLandmarkFavorite}
                        onDelete={deleteLandmark}
                    />

                    {selectedLandmark ? (
                        <LandmarkDetail
                            selectedLandmark={selectedLandmark}
                            selectedName={selectedName}
                            visiblePoints={visiblePoints}
                            onFlyTo={handleSelectedLandmarkFlyTo}
                            onRename={handleSelectedLandmarkRename}
                            now={now}
                        />
                    ) : (
                        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                            <div className="text-center px-4">
                                <svg className="w-8 h-8 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                                </svg>
                                <div className="text-xs leading-relaxed">
                                    Select a landmark above, or click<br />
                                    any point on a fiber line on the map
                                </div>
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Sections tab content */}
            {activeTab === 'sections' && hasSections && (
                <div className="flex-1 flex flex-col overflow-hidden">
                    <SectionList
                        sections={sectionsArray}
                        fibers={fibers}
                        sectionStats={sectionStats}
                        selectedSectionId={selectedSection?.sectionId ?? null}
                        onSelect={handleSectionSelect}
                        onFlyTo={handleSectionFlyTo}
                        onRename={renameSection}
                        onDelete={deleteSection}
                        onToggleFavorite={toggleSectionFavorite}
                    />

                    {selectedSection ? (() => {
                        const fullStats = sectionStats.get(selectedSection.sectionId)
                        const historyData = sectionData.get(selectedSection.sectionId) || []
                        if (!fullStats) return null

                        return (
                            <SectionDetail
                                stats={fullStats}
                                historyData={historyData}
                                now={now}
                            />
                        )
                    })() : (
                        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                            <div className="text-center px-4">
                                <svg className="w-8 h-8 mx-auto mb-2 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                                </svg>
                                <div className="text-xs leading-relaxed">
                                    Select a section above to view<br />
                                    detailed traffic statistics
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
