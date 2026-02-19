import { useSection } from '@/hooks/useSection'
import { useFibers } from '@/hooks/useFibers'

export function SectionCreationIndicator() {
    const { sectionCreationMode, pendingPoint, setPendingPoint, setSectionCreationMode, previewChannel } = useSection()
    const { fibers } = useFibers()

    const isActive = sectionCreationMode || pendingPoint !== null

    if (!isActive) return null

    const fiber = pendingPoint ? fibers.find(f => f.id === pendingPoint.fiberId) : null
    const fiberName = fiber?.name || pendingPoint?.fiberId || ''

    // Calculate the channel range for display
    const startChannel = pendingPoint && previewChannel !== null
        ? Math.min(pendingPoint.channel, previewChannel)
        : null
    const endChannel = pendingPoint && previewChannel !== null
        ? Math.max(pendingPoint.channel, previewChannel)
        : null
    const channelCount = startChannel !== null && endChannel !== null
        ? endChannel - startChannel
        : null

    const handleCancel = () => {
        setPendingPoint(null)
        setSectionCreationMode(false)
    }

    return (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] pointer-events-auto">
            <div className="bg-amber-500 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-3">
                <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
                    </span>
                    <span className="text-sm font-medium">
                        {pendingPoint ? (
                            <>
                                <span className="font-semibold">{fiberName}</span>
                                {' '}— {startChannel !== null && endChannel !== null ? (
                                    <>
                                        Ch {startChannel} → {endChannel}
                                        <span className="opacity-75 ml-1">({channelCount} channels)</span>
                                    </>
                                ) : (
                                    <>Ch {pendingPoint.channel} selected</>
                                )}
                                <span className="opacity-75 ml-2">· Click to complete</span>
                            </>
                        ) : (
                            'Click on a fiber to start section'
                        )}
                    </span>
                </div>
                <button
                    onClick={handleCancel}
                    className="ml-2 text-white/80 hover:text-white text-xs font-medium px-2 py-0.5 rounded hover:bg-white/20 transition-colors"
                >
                    Cancel
                </button>
            </div>
        </div>
    )
}
