import { useMemo } from 'react'
import { useLandmarkSelection } from '@/hooks/useLandmarkSelection'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'
import { useSectionStats } from '@/hooks/useSectionStats'
import { useDashboardState } from '@/context/DashboardContext'
import { LandmarkList } from './LandmarkList'
import { LandmarkDetail } from './LandmarkDetail'
import { TrafficMonitorActionsProvider } from './TrafficMonitorContext'
import { SectionList } from './SectionList'
import { SectionDetail } from './SectionDetail'
import { TrafficTabs, TrafficEmptyState, TrafficSelectionPrompt } from './TrafficDetailPanel'
import { useTrafficData } from './useTrafficData'
import { useTrafficHandlers } from './useTrafficHandlers'

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
    const { sections, selectSection, selectedSection, renameSection, deleteSection, toggleSectionFavorite } = useSection()
    const { stats: sectionStats } = useSectionStats(sections)
    const { widgetStates, setTrafficMonitorTab } = useDashboardState()

    const activeTab = widgetStates.trafficMonitorTab

    // Convert sections Map to array
    const sectionsArray = useMemo(() => {
        return Array.from(sections.values())
    }, [sections])

    // Get traffic data
    const {
        landmarks,
        landmarkData,
        sectionData,
        visiblePoints,
        now
    } = useTrafficData({
        landmarksMap,
        selectedLandmark,
        sectionsArray
    })

    // Get event handlers
    const {
        handleSectionSelect,
        handleSectionFlyTo,
        handleSelectedLandmarkRename,
        handleSelectedLandmarkFlyTo,
        landmarkActions
    } = useTrafficHandlers({
        selectedLandmark,
        sections,
        fibers,
        selectLandmark,
        selectSection,
        renameLandmark,
        toggleLandmarkFavorite,
        deleteLandmark,
    })

    const hasLandmarks = landmarks.length > 0
    const hasSections = sectionsArray.length > 0
    const showLandmarkEmptyState = !hasLandmarks && !selectedLandmark
    const showEmptyState = (activeTab === 'landmarks' && showLandmarkEmptyState) || (activeTab === 'sections' && !hasSections)

    const selectedKey = selectedLandmark ? `${selectedLandmark.fiberId}:${selectedLandmark.channel}` : null
    const selectedName = selectedLandmark ? getLandmarkName(selectedLandmark.fiberId, selectedLandmark.channel) : null

    return (
        <div className="h-full flex flex-col bg-white overflow-hidden">
            <TrafficTabs
                activeTab={activeTab}
                hasLandmarks={landmarks.length}
                hasSections={sectionsArray.length}
                onTabChange={setTrafficMonitorTab}
            />

            {showEmptyState && <TrafficEmptyState activeTab={activeTab} />}

            {/* Landmarks tab content */}
            {activeTab === 'landmarks' && (hasLandmarks || selectedLandmark) && (
                <>
                    <TrafficMonitorActionsProvider actions={landmarkActions}>
                        <LandmarkList
                            landmarks={landmarks}
                            fibers={fibers}
                            landmarkData={landmarkData}
                            selectedKey={selectedKey}
                            now={now}
                        />
                    </TrafficMonitorActionsProvider>

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
                        <TrafficSelectionPrompt activeTab={activeTab} />
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
                        <TrafficSelectionPrompt activeTab={activeTab} />
                    )}
                </div>
            )}
        </div>
    )
}
