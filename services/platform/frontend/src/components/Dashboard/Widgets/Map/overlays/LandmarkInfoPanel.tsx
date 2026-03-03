import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useFibers } from '@/hooks/useFibers'
import { useLandmarkSelection } from "@/hooks/useLandmarkSelection"
import { useDashboardState } from '@/context/DashboardContext'

/**
 * Panel showing selected landmark info with editable name.
 * Rendered as overlay on map.
 * Visibility controlled by DashboardContext ownership.
 */
export function LandmarkInfoPanel() {
    const { t } = useTranslation()
    const { selectedLandmark, selectLandmark, getLandmarkName, renameLandmark } = useLandmarkSelection()
    const { fibers } = useFibers()
    const { ownership } = useDashboardState()

    const [editingName, setEditingName] = useState(false)
    const [confirmingDelete, setConfirmingDelete] = useState(false)

    const landmarkKey = selectedLandmark ? `${selectedLandmark.fiberId}:${selectedLandmark.channel}` : null
    const initialName = selectedLandmark ? getLandmarkName(selectedLandmark.fiberId, selectedLandmark.channel) ?? '' : ''

    const [nameInput, setNameInput] = useState(initialName)

    useEffect(() => {
        setNameInput(initialName)
        setEditingName(false)
        setConfirmingDelete(false)
    }, [landmarkKey, initialName])

    // Visibility controlled by ownership
    if (!ownership.landmarkInfo) return null
    if (!selectedLandmark) return null

    const fiber = fibers.find(f => f.id === selectedLandmark.fiberId)
    const landmarkName = getLandmarkName(selectedLandmark.fiberId, selectedLandmark.channel)

    const handleSaveName = () => {
        renameLandmark(selectedLandmark.fiberId, selectedLandmark.channel, nameInput)
        setEditingName(false)
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleSaveName()
        } else if (e.key === 'Escape') {
            setEditingName(false)
            setNameInput(landmarkName ?? '')
        }
    }

    const handleDeleteClick = () => {
        if (!landmarkName) return
        if (confirmingDelete) {
            // Confirm - actually delete and deselect
            renameLandmark(selectedLandmark.fiberId, selectedLandmark.channel, '')
            selectLandmark(null)
            setConfirmingDelete(false)
        } else {
            // First click - enter confirmation mode
            setConfirmingDelete(true)
        }
    }

    return (
        <div className="absolute top-3 md:right-[60px] right-2 bg-white rounded-lg p-3 shadow-lg text-[13px] z-[1000] min-w-[220px] pointer-events-auto max-h-[calc(100vh-8rem)] md:max-h-none overflow-y-auto">
            <div className="flex justify-between items-center mb-2">
                <strong className="text-slate-700">{t('map.landmark.selectedTitle')}</strong>
                <div className="flex items-center gap-2">
                    {landmarkName && (
                        <button
                            onMouseDown={(e) => {
                                e.preventDefault() // Prevent blur from firing before click
                                handleDeleteClick()
                            }}
                            onBlur={() => setConfirmingDelete(false)}
                            className={`bg-transparent border-none cursor-pointer text-xs min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 flex items-center justify-center leading-none transition-colors ${
                                confirmingDelete
                                    ? 'text-red-600 font-semibold'
                                    : 'text-red-400 hover:text-red-600'
                            }`}
                            title={confirmingDelete ? t('common.clickToConfirm') : t('map.landmark.deleteLabel')}
                        >
                            {confirmingDelete ? 'Confirm?' : 'Delete'}
                        </button>
                    )}
                    <button
                        onClick={() => selectLandmark(null)}
                        className="bg-transparent border-none cursor-pointer text-slate-400 text-base min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 flex items-center justify-center p-0 leading-none hover:text-slate-600"
                    >
                        ×
                    </button>
                </div>
            </div>

            <div className="text-slate-500 leading-[1.8]">
                {/* Name field */}
                <div className="mb-2">
                    <span className="text-slate-400">{`${t('common.name')}: `}</span>
                    {editingName ? (
                        <span className="inline-flex gap-1">
                            <input
                                type="text"
                                value={nameInput}
                                onChange={(e) => setNameInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                onBlur={handleSaveName}
                                autoFocus
                                className="border border-slate-300 rounded px-1.5 py-0.5 text-[13px] w-[120px] focus:outline-none focus:ring-1 focus:ring-blue-500"
                                placeholder={t('map.landmark.enterName')}
                            />
                        </span>
                    ) : (
                        <span
                            onClick={() => setEditingName(true)}
                            className={`cursor-pointer border-b border-dashed border-slate-300 ${
                                landmarkName ? 'text-slate-700' : 'text-slate-400'
                            } hover:border-blue-400`}
                            title={t('common.clickToEdit')}
                        >
                            {landmarkName || t('map.landmark.clickToName')}
                        </span>
                    )}
                </div>

                <div>
                    <span className="text-slate-400">{`${t('common.fiber')}: `}</span>
                    {fiber?.name || selectedLandmark.fiberId}
                </div>
                <div>
                    <span className="text-slate-400">{`${t('common.channel')}: `}</span>
                    {selectedLandmark.channel}
                </div>
                <div>
                    <span className="text-slate-400">{`${t('common.position')}: `}</span>
                    {selectedLandmark.lat.toFixed(5)}, {selectedLandmark.lng.toFixed(5)}
                </div>
            </div>
        </div>
    )
}
