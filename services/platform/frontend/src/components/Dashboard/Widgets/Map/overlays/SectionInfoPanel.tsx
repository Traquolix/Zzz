import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'
import { useDashboardState } from '@/context/DashboardContext'

export function SectionInfoPanel() {
    const { t } = useTranslation()
    const { ownership } = useDashboardState()
    const {
        sections,
        selectedSection,
        selectSection,
        renameSection,
        deleteSection
    } = useSection()
    const { fibers } = useFibers()
    const [editingName, setEditingName] = useState(false)
    const [nameInput, setNameInput] = useState('')
    const [confirmingDelete, setConfirmingDelete] = useState(false)

    const section = selectedSection ? sections.get(selectedSection.sectionId) : null

    useEffect(() => {
        if (section) {
            setNameInput(section.name)
            setEditingName(false)
            setConfirmingDelete(false)
        }
    }, [selectedSection?.sectionId, section])

    // Visibility controlled by ownership
    if (!ownership.sectionInfo) return null
    if (!selectedSection || !section) return null

    const fiber = fibers.find(f => f.id === section.fiberId)

    const handleSaveName = () => {
        if (nameInput.trim()) {
            renameSection(section.id, nameInput)
        }
        setEditingName(false)
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleSaveName()
        } else if (e.key === 'Escape') {
            setEditingName(false)
            setNameInput(section.name)
        }
    }

    const handleDeleteClick = () => {
        if (confirmingDelete) {
            // Confirm - actually delete
            deleteSection(section.id)
            setConfirmingDelete(false)
        } else {
            // First click - enter confirmation mode
            setConfirmingDelete(true)
        }
    }

    const channelCount = section.endChannel - section.startChannel + 1

    return (
        <div className="absolute top-3 right-[60px] bg-white rounded-lg p-3 shadow-lg text-[13px] z-[1000] min-w-[220px] pointer-events-auto">
            <div className="flex justify-between items-center mb-2">
                <strong className="text-slate-700">{t('map.section.selectedTitle')}</strong>
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleDeleteClick}
                        onBlur={() => setConfirmingDelete(false)}
                        className={`bg-transparent border-none cursor-pointer text-xs p-0 leading-none transition-colors ${
                            confirmingDelete
                                ? 'text-red-600 font-semibold'
                                : 'text-red-400 hover:text-red-600'
                        }`}
                        title={confirmingDelete ? t('common.clickToConfirm') : t('map.section.deleteSection')}
                    >
                        {confirmingDelete ? 'Confirm?' : 'Delete'}
                    </button>
                    <button
                        onClick={() => selectSection(null)}
                        className="bg-transparent border-none cursor-pointer text-slate-400 text-base p-0 leading-none hover:text-slate-600"
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
                                className="border border-slate-300 rounded px-1.5 py-0.5 text-[13px] w-[140px] focus:outline-none focus:ring-1 focus:ring-green-500"
                                placeholder={t('map.section.namePlaceholder')}
                            />
                        </span>
                    ) : (
                        <span
                            onClick={() => setEditingName(true)}
                            className="cursor-pointer border-b border-dashed border-slate-300 text-slate-700 hover:border-green-400"
                            title={t('common.clickToEdit')}
                        >
                            {section.name}
                        </span>
                    )}
                </div>

                <div>
                    <span className="text-slate-400">{`${t('common.fiber')}: `}</span>
                    {fiber?.name || section.fiberId}
                </div>
                <div>
                    <span className="text-slate-400">{t('map.section.channels')} </span>
                    {section.startChannel} - {section.endChannel} ({channelCount} {t('map.section.sensors')})
                </div>

                {/* Resize hint */}
                <div className="mt-3 pt-2 border-t border-slate-100 text-xs text-slate-400">
                    {t('map.section.resizeHint')}
                </div>
            </div>
        </div>
    )
}
