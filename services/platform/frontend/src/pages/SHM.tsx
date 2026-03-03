import { useState, useCallback, useContext, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Building2, MapPin, X, Map, List } from 'lucide-react'
import { InfrastructureDataProvider } from '@/context/InfrastructureProvider'
import { InfrastructureDataContext } from '@/context/InfrastructureContext'
import { SpectralHeatmap, PeakFrequencyScatter, TimeComparison, SHMMap, DaySelector, StatusDot, MiniPeakChart } from '@/components/SHM'
import { formatDuration } from '@/lib/formatters'
import { useSHMData } from '@/hooks/useSHMData'
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton'
import type { Infrastructure } from '@/types/infrastructure'

type ViewMode = 'map' | 'list'

const TYPE_ICONS: Record<string, typeof Building2> = {
    bridge: Building2,
    tunnel: MapPin
}

function SHMContent() {
    const dataContext = useContext(InfrastructureDataContext)
    if (!dataContext) {
        throw new Error('SHMContent must be used within InfrastructureDataProvider')
    }
    const { infrastructures, loading } = dataContext

    const [viewMode, setViewMode] = useState<ViewMode>('map')

    const {
        selectedInfrastructure,
        handleSelect: rawHandleSelect,
        handleDeselect,
        dataSummary,
        selectedDay,
        setSelectedDay,
        spectralData,
        spectralLoading,
        spectralError,
        peakData,
        peakLoading,
        shmStatus,
    } = useSHMData()

    // Wrap handleSelect to also switch to map view
    const handleSelect = useCallback((infra: Infrastructure) => {
        rawHandleSelect(infra)
        setViewMode('map')
    }, [rawHandleSelect])

    // Container ref for measuring available width
    const detailContainerRef = useRef<HTMLDivElement>(null)
    const [chartWidth, setChartWidth] = useState(600)

    const { t } = useTranslation()

    // Measure container width for responsive charts
    useEffect(() => {
        if (!detailContainerRef.current) return

        const measure = () => {
            if (detailContainerRef.current) {
                const availableWidth = detailContainerRef.current.clientWidth - 40
                setChartWidth(Math.max(300, availableWidth))
            }
        }

        measure()

        const resizer = new ResizeObserver(measure)
        resizer.observe(detailContainerRef.current)

        return () => resizer.disconnect()
    }, [selectedInfrastructure])

    // View toggle button
    const viewToggle = (
        <div className="absolute top-4 left-4 z-10 bg-white dark:bg-slate-900 rounded-lg shadow-md border border-slate-200 dark:border-slate-700 p-1 flex gap-1">
            <button
                onClick={() => setViewMode('map')}
                className={`p-2 rounded-md transition-colors ${
                    viewMode === 'map' ? 'bg-blue-500 text-white' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
                title="Map view"
            >
                <Map className="w-4 h-4" />
            </button>
            <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded-md transition-colors ${
                    viewMode === 'list' ? 'bg-blue-500 text-white' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
                title="List view"
            >
                <List className="w-4 h-4" />
            </button>
        </div>
    )

    // Infrastructure list component - 3 column layout
    const infraList = (
        <div className="p-4 space-y-3">
            {loading ? (
                <div className="flex items-center justify-center h-64 px-4">
                    <Skeleton lines={8} className="w-full" />
                </div>
            ) : infrastructures.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-64 text-slate-400">
                    <Building2 className="h-12 w-12 mb-3" />
                    <p className="text-lg font-medium">{t('shm.noInfrastructure', 'No infrastructure configured')}</p>
                    <p className="text-sm">{t('shm.noInfrastructureDesc', 'Bridges and tunnels will appear here')}</p>
                </div>
            ) : (
                infrastructures.map(infra => {
                    const isSelected = selectedInfrastructure?.id === infra.id
                    const Icon = TYPE_ICONS[infra.type] || Building2

                    return (
                        <div
                            key={infra.id}
                            onClick={() => handleSelect(infra)}
                            className={`rounded-lg border cursor-pointer transition-all ${
                                isSelected
                                    ? 'border-2 border-slate-300 dark:border-slate-600 shadow-md bg-slate-50 dark:bg-slate-800'
                                    : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:shadow-sm bg-white dark:bg-slate-900'
                            }`}
                        >
                            <div className="flex items-stretch">
                                {/* Column 1: Image */}
                                <div className="w-28 flex-shrink-0 bg-slate-100 dark:bg-slate-800 rounded-l-lg overflow-hidden">
                                    {infra.imageUrl ? (
                                        <img
                                            src={infra.imageUrl}
                                            alt={infra.name}
                                            className="w-full h-full object-cover"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center">
                                            <Icon className="h-8 w-8 text-slate-300" />
                                        </div>
                                    )}
                                </div>

                                {/* Column 2: Info */}
                                <div className="flex-1 p-4 flex flex-col justify-center">
                                    <div className="flex items-center gap-2">
                                        <StatusDot status={shmStatus?.status ?? 'nominal'} size="sm" shmData={shmStatus} />
                                        <h3 className="font-medium text-slate-900 dark:text-slate-100">{infra.name}</h3>
                                    </div>
                                    <p className="text-sm text-slate-500 dark:text-slate-400 capitalize mt-0.5">{infra.type}</p>
                                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                                        {infra.fiberId} &bull; Ch {infra.startChannel}&ndash;{infra.endChannel}
                                    </p>
                                </div>

                                {/* Column 3: Mini Peak Chart */}
                                <div className="w-48 flex-shrink-0 p-3 flex items-center border-l border-slate-100 dark:border-slate-800">
                                    <MiniPeakChart infrastructureId={infra.id} width={168} height={52} />
                                </div>
                            </div>
                        </div>
                    )
                })
            )}
        </div>
    )

    // Detail panel content
    const detailPanel = selectedInfrastructure && (
        <div className="h-full overflow-hidden bg-slate-50 dark:bg-slate-950" data-detail-panel>
        <div ref={detailContainerRef} className="h-full overflow-y-auto overflow-x-hidden p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <div className="flex items-center gap-2">
                        <StatusDot status={shmStatus?.status ?? 'nominal'} shmData={shmStatus} />
                        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{selectedInfrastructure.name}</h2>
                    </div>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                        {selectedInfrastructure.type} &bull; {selectedInfrastructure.fiberId} &bull; Ch {selectedInfrastructure.startChannel}&ndash;{selectedInfrastructure.endChannel}
                    </p>
                </div>
                <button
                    onClick={handleDeselect}
                    className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                >
                    <X className="w-5 h-5 text-slate-400 dark:text-slate-500" />
                </button>
            </div>

            {/* Day selector */}
            {dataSummary && (
                <div className="flex items-center gap-3 mb-6">
                    <span className="text-sm text-slate-500 dark:text-slate-400">{t('shm.viewingData', 'Viewing data for')}:</span>
                    <DaySelector
                        dataStart={new Date(dataSummary.t0)}
                        dataEnd={new Date(dataSummary.endTime)}
                        selectedDay={selectedDay}
                        onSelectDay={setSelectedDay}
                    />
                </div>
            )}

            {/* Spectral visualizations */}
            {spectralLoading ? (
                <div className="flex items-center justify-center h-64">
                    <TableSkeleton rows={3} cols={4} />
                </div>
            ) : spectralError ? (
                <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-8 text-center">
                    <p className="text-slate-500 dark:text-slate-400">{spectralError}</p>
                    <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">{t('shm.spectralErrorDesc', 'Sample data may not be available')}</p>
                </div>
            ) : spectralData && peakData ? (
                <div className="space-y-6">
                    {/* Spectral heatmap */}
                    <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                        <div className="flex items-center justify-between mb-3">
                            <div>
                                <h3 className="text-base font-medium text-slate-900 dark:text-slate-100">
                                    {t('shm.spectralHeatmap', 'Spectral Heatmap')}
                                </h3>
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                    {t('shm.heatmapDesc', 'Power spectrum over time (log scale)')}
                                </p>
                            </div>
                            <div className="text-xs text-slate-400 dark:text-slate-500">
                                {spectralData.numTimeSamples} &times; {spectralData.numFreqBins}
                            </div>
                        </div>
                        <div className="pb-6">
                            <SpectralHeatmap data={spectralData} width={chartWidth} height={280} />
                        </div>
                    </div>

                    {/* Peak frequency scatter plot */}
                    <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                        <div className="mb-3">
                            <h3 className="text-base font-medium text-slate-900 dark:text-slate-100">
                                {t('shm.peakFrequencies', 'Peak Frequencies')}
                            </h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                {t('shm.peakDesc', 'Dominant frequency at each time sample')}
                            </p>
                        </div>
                        {peakLoading ? (
                            <div className="flex items-center justify-center h-[180px]">
                                <TableSkeleton rows={2} cols={3} />
                            </div>
                        ) : (
                            <PeakFrequencyScatter data={peakData} width={chartWidth} height={180} />
                        )}
                    </div>

                    {/* Time window comparison */}
                    <TimeComparison dataSummary={dataSummary} selectedDay={selectedDay} />

                    {/* Data info */}
                    <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                                <span className="text-slate-500 dark:text-slate-400">{t('shm.startTime', 'Start')}:</span>
                                <p className="font-medium text-slate-900 dark:text-slate-100 text-xs">
                                    {new Date(spectralData.t0).toLocaleString()}
                                </p>
                            </div>
                            <div>
                                <span className="text-slate-500 dark:text-slate-400">{t('shm.duration', 'Duration')}:</span>
                                <p className="font-medium text-slate-900 dark:text-slate-100">
                                    {formatDuration(spectralData.durationSeconds)}
                                </p>
                            </div>
                            <div>
                                <span className="text-slate-500 dark:text-slate-400">{t('shm.freqRange', 'Freq range')}:</span>
                                <p className="font-medium text-slate-900 dark:text-slate-100">
                                    {spectralData.freqRange[0].toFixed(1)} - {spectralData.freqRange[1].toFixed(1)} Hz
                                </p>
                            </div>
                            <div>
                                <span className="text-slate-500 dark:text-slate-400">{t('shm.samples', 'Samples')}:</span>
                                <p className="font-medium text-slate-900 dark:text-slate-100">
                                    {spectralData.numTimeSamples.toLocaleString()}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-8 text-center">
                    <p className="text-slate-400 dark:text-slate-500">{t('shm.noSpectralData', 'No spectral data available')}</p>
                </div>
            )}
        </div>
        </div>
    )

    // List view is always full screen
    if (viewMode === 'list') {
        return (
            <div className="h-full relative">
                {viewToggle}
                <div className="h-full overflow-auto bg-slate-50 dark:bg-slate-950 flex justify-center">
                    <div className="w-1/2 bg-white dark:bg-slate-900 h-fit my-8 rounded-lg border border-slate-200 dark:border-slate-700">
                        {infraList}
                    </div>
                </div>
            </div>
        )
    }

    // Map view - full screen when no selection, split when selected
    if (!selectedInfrastructure) {
        return (
            <div className="h-full relative">
                {viewToggle}
                <SHMMap
                    infrastructures={infrastructures}
                    selectedInfrastructure={selectedInfrastructure}
                    onSelect={handleSelect}
                    className="rounded-none"
                />
            </div>
        )
    }

    // Map view with selection - split view (1/4 map left, 3/4 details right)
    return (
        <div className="h-full flex">
            {/* Left: Map (1/4 width) */}
            <div className="w-1/4 flex-none relative border-r border-slate-200 dark:border-slate-700">
                {viewToggle}
                <SHMMap
                    infrastructures={infrastructures}
                    selectedInfrastructure={selectedInfrastructure}
                    onSelect={handleSelect}
                />
            </div>

            {/* Right: Details (takes remaining space) */}
            <div className="flex-1 min-w-0">
                {detailPanel}
            </div>
        </div>
    )
}

export function SHM() {
    return (
        <InfrastructureDataProvider>
            <SHMContent />
        </InfrastructureDataProvider>
    )
}
