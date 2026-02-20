import { useState, useEffect, useCallback, useContext, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Building2, MapPin, X, Map, List } from 'lucide-react'
import { InfrastructureDataProvider } from '@/context/InfrastructureProvider'
import { InfrastructureDataContext } from '@/context/InfrastructureContext'
import { SpectralHeatmap, PeakFrequencyScatter, TimeComparison, SHMMap, DaySelector, getDayTimeRange, StatusDot, MiniPeakChart } from '@/components/SHM'
import { fetchSpectralData, fetchPeakFrequencies, fetchSpectralSummary } from '@/api/infrastructure'
import type { Infrastructure, SelectedInfrastructure, SpectralTimeSeries, PeakFrequencyData, SpectralSummary } from '@/types/infrastructure'

type ViewMode = 'map' | 'list'

const TYPE_ICONS: Record<string, typeof Building2> = {
    bridge: Building2,
    tunnel: MapPin
}

function formatDuration(seconds: number): string {
    if (seconds < 60) {
        return `${seconds.toFixed(1)}s`
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60)
        const secs = Math.round(seconds % 60)
        return `${mins}m ${secs}s`
    } else if (seconds < 86400) {
        const hrs = Math.floor(seconds / 3600)
        const mins = Math.round((seconds % 3600) / 60)
        // Handle rounding overflow (60m -> 1h)
        if (mins === 60) {
            return `${hrs + 1}h 0m`
        }
        return `${hrs}h ${mins}m`
    } else {
        const days = Math.floor(seconds / 86400)
        const hrs = Math.round((seconds % 86400) / 3600)
        // Handle rounding overflow (24h -> 1d)
        if (hrs === 24) {
            return `${days + 1}d 0h`
        }
        return `${days}d ${hrs}h`
    }
}

function SHMContent() {
    const dataContext = useContext(InfrastructureDataContext)
    if (!dataContext) {
        throw new Error('SHMContent must be used within InfrastructureDataProvider')
    }
    const { infrastructures, loading } = dataContext

    const [viewMode, setViewMode] = useState<ViewMode>('map')
    const [selectedInfrastructure, setSelectedInfrastructure] = useState<SelectedInfrastructure | null>(null)

    // Data summary and selected day for unified time filtering
    const [dataSummary, setDataSummary] = useState<SpectralSummary | null>(null)
    const [selectedDay, setSelectedDay] = useState<Date | null>(null)

    const [spectralData, setSpectralData] = useState<SpectralTimeSeries | null>(null)
    const [peakData, setPeakData] = useState<PeakFrequencyData | null>(null)
    const [spectralLoading, setSpectralLoading] = useState(false)
    const [peakLoading, setPeakLoading] = useState(false)
    const [spectralError, setSpectralError] = useState<string | null>(null)

    // Container ref for measuring available width
    const detailContainerRef = useRef<HTMLDivElement>(null)
    const [chartWidth, setChartWidth] = useState(600)

    const { t } = useTranslation()

    // Measure container width for responsive charts
    useEffect(() => {
        if (!detailContainerRef.current) return

        const measure = () => {
            if (detailContainerRef.current) {
                // Account for padding (p-5 = 20px each side = 40px total)
                const availableWidth = detailContainerRef.current.clientWidth - 40
                setChartWidth(Math.max(300, availableWidth))
            }
        }

        measure()

        const resizer = new ResizeObserver(measure)
        resizer.observe(detailContainerRef.current)

        return () => resizer.disconnect()
    }, [selectedInfrastructure])

    // Fetch data summary to get available date range (default to All time)
    useEffect(() => {
        if (!selectedInfrastructure) return

        async function loadSummary() {
            try {
                const summary = await fetchSpectralSummary()
                setDataSummary(summary)
                // Default to "All time" (null)
                setSelectedDay(null)
            } catch (err) {
                console.error('Failed to load spectral summary:', err)
            }
        }
        loadSummary()
    }, [selectedInfrastructure])

    // Load spectral data when an infrastructure is selected or day changes
    useEffect(() => {
        if (!selectedInfrastructure) {
            setSpectralData(null)
            setPeakData(null)
            return
        }

        async function loadSpectralData() {
            setSpectralLoading(true)
            setSpectralError(null)
            try {
                const timeRange = getDayTimeRange(selectedDay)
                const spectra = await fetchSpectralData({
                    maxTimeSamples: 10000,
                    maxFreqBins: 400,
                    startTime: timeRange?.from,
                    endTime: timeRange?.to,
                })
                setSpectralData(spectra)
            } catch (err) {
                console.error('Failed to load spectral data:', err)
                setSpectralError(t('shm.spectralLoadError', 'Failed to load spectral data'))
            } finally {
                setSpectralLoading(false)
            }
        }
        loadSpectralData()
    }, [selectedInfrastructure, selectedDay, t])

    // Load peak data when infrastructure or day changes
    useEffect(() => {
        if (!selectedInfrastructure) return

        async function loadPeakData() {
            setPeakLoading(true)
            try {
                const timeRange = getDayTimeRange(selectedDay)
                const peaks = await fetchPeakFrequencies({
                    maxSamples: 10000,
                    startTime: timeRange?.from,
                    endTime: timeRange?.to,
                })
                setPeakData(peaks)
            } catch (err) {
                console.error('Failed to load peak data:', err)
            } finally {
                setPeakLoading(false)
            }
        }
        loadPeakData()
    }, [selectedInfrastructure, selectedDay])

    // Handle escape key to deselect
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && selectedInfrastructure) {
                setSelectedInfrastructure(null)
            }
        }
        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [selectedInfrastructure])

    const handleSelect = useCallback((infra: Infrastructure) => {
        setSelectedInfrastructure({
            id: infra.id,
            name: infra.name,
            type: infra.type,
            fiberId: infra.fiberId,
            startChannel: infra.startChannel,
            endChannel: infra.endChannel
        })
        // Always switch to map view when selecting (list view is browse-only)
        setViewMode('map')
    }, [])

    const handleDeselect = useCallback(() => {
        setSelectedInfrastructure(null)
    }, [])

    // View toggle button
    const viewToggle = (
        <div className="absolute top-4 left-4 z-10 bg-white rounded-lg shadow-md border border-slate-200 p-1 flex gap-1">
            <button
                onClick={() => setViewMode('map')}
                className={`p-2 rounded-md transition-colors ${
                    viewMode === 'map' ? 'bg-blue-500 text-white' : 'text-slate-500 hover:bg-slate-100'
                }`}
                title="Map view"
            >
                <Map className="w-4 h-4" />
            </button>
            <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded-md transition-colors ${
                    viewMode === 'list' ? 'bg-blue-500 text-white' : 'text-slate-500 hover:bg-slate-100'
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
                <div className="flex items-center justify-center h-64">
                    <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
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
                                    ? 'border-2 border-slate-300 shadow-md bg-slate-50'
                                    : 'border-slate-200 hover:border-slate-300 hover:shadow-sm bg-white'
                            }`}
                        >
                            <div className="flex items-stretch">
                                {/* Column 1: Image */}
                                <div className="w-28 flex-shrink-0 bg-slate-100 rounded-l-lg overflow-hidden">
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
                                        <StatusDot status="nominal" size="sm" />
                                        <h3 className="font-medium text-slate-900">{infra.name}</h3>
                                    </div>
                                    <p className="text-sm text-slate-500 capitalize mt-0.5">{infra.type}</p>
                                    <p className="text-xs text-slate-400 mt-1">
                                        {infra.fiberId} &bull; Ch {infra.startChannel}&ndash;{infra.endChannel}
                                    </p>
                                </div>

                                {/* Column 3: Mini Peak Chart */}
                                <div className="w-48 flex-shrink-0 p-3 flex items-center border-l border-slate-100">
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
        <div className="h-full overflow-hidden bg-slate-50" data-detail-panel>
        <div ref={detailContainerRef} className="h-full overflow-y-auto overflow-x-hidden p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <div className="flex items-center gap-2">
                        <StatusDot status="nominal" />
                        <h2 className="text-xl font-semibold text-slate-900">{selectedInfrastructure.name}</h2>
                    </div>
                    <p className="text-sm text-slate-500">
                        {selectedInfrastructure.type} &bull; {selectedInfrastructure.fiberId} &bull; Ch {selectedInfrastructure.startChannel}&ndash;{selectedInfrastructure.endChannel}
                    </p>
                </div>
                <button
                    onClick={handleDeselect}
                    className="p-2 hover:bg-white rounded-lg transition-colors"
                >
                    <X className="w-5 h-5 text-slate-400" />
                </button>
            </div>

            {/* Day selector */}
            {dataSummary && (
                <div className="flex items-center gap-3 mb-6">
                    <span className="text-sm text-slate-500">{t('shm.viewingData', 'Viewing data for')}:</span>
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
                    <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
                    <span className="ml-3 text-slate-500">{t('shm.loadingSpectral', 'Loading spectral data...')}</span>
                </div>
            ) : spectralError ? (
                <div className="bg-white rounded-lg border border-slate-200 p-8 text-center">
                    <p className="text-slate-500">{spectralError}</p>
                    <p className="text-sm text-slate-400 mt-1">{t('shm.spectralErrorDesc', 'Sample data may not be available')}</p>
                </div>
            ) : spectralData && peakData ? (
                <div className="space-y-6">
                    {/* Spectral heatmap */}
                    <div className="bg-white rounded-lg border border-slate-200 p-5">
                        <div className="flex items-center justify-between mb-3">
                            <div>
                                <h3 className="text-base font-medium text-slate-900">
                                    {t('shm.spectralHeatmap', 'Spectral Heatmap')}
                                </h3>
                                <p className="text-xs text-slate-500">
                                    {t('shm.heatmapDesc', 'Power spectrum over time (log scale)')}
                                </p>
                            </div>
                            <div className="text-xs text-slate-400">
                                {spectralData.numTimeSamples} &times; {spectralData.numFreqBins}
                            </div>
                        </div>
                        <div className="pb-6">
                            <SpectralHeatmap data={spectralData} width={chartWidth} height={280} />
                        </div>
                    </div>

                    {/* Peak frequency scatter plot */}
                    <div className="bg-white rounded-lg border border-slate-200 p-5">
                        <div className="mb-3">
                            <h3 className="text-base font-medium text-slate-900">
                                {t('shm.peakFrequencies', 'Peak Frequencies')}
                            </h3>
                            <p className="text-xs text-slate-500">
                                {t('shm.peakDesc', 'Dominant frequency at each time sample')}
                            </p>
                        </div>
                        {peakLoading ? (
                            <div className="flex items-center justify-center h-[180px]">
                                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                            </div>
                        ) : (
                            <PeakFrequencyScatter data={peakData} width={chartWidth} height={180} />
                        )}
                    </div>

                    {/* Time window comparison */}
                    <TimeComparison dataSummary={dataSummary} selectedDay={selectedDay} />

                    {/* Data info */}
                    <div className="bg-white rounded-lg border border-slate-200 p-4">
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                                <span className="text-slate-500">{t('shm.startTime', 'Start')}:</span>
                                <p className="font-medium text-slate-900 text-xs">
                                    {new Date(spectralData.t0).toLocaleString()}
                                </p>
                            </div>
                            <div>
                                <span className="text-slate-500">{t('shm.duration', 'Duration')}:</span>
                                <p className="font-medium text-slate-900">
                                    {formatDuration(spectralData.durationSeconds)}
                                </p>
                            </div>
                            <div>
                                <span className="text-slate-500">{t('shm.freqRange', 'Freq range')}:</span>
                                <p className="font-medium text-slate-900">
                                    {spectralData.freqRange[0].toFixed(1)} - {spectralData.freqRange[1].toFixed(1)} Hz
                                </p>
                            </div>
                            <div>
                                <span className="text-slate-500">{t('shm.samples', 'Samples')}:</span>
                                <p className="font-medium text-slate-900">
                                    {spectralData.numTimeSamples.toLocaleString()}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="bg-white rounded-lg border border-slate-200 p-8 text-center">
                    <p className="text-slate-400">{t('shm.noSpectralData', 'No spectral data available')}</p>
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
                <div className="h-full overflow-auto bg-slate-50 flex justify-center">
                    <div className="w-1/2 bg-white h-fit my-8 rounded-lg border border-slate-200">
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
            <div className="w-1/4 flex-none relative border-r border-slate-200">
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
