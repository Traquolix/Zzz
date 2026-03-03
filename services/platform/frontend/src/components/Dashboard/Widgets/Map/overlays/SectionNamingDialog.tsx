import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useFibers } from '@/hooks/useFibers'
import { useSection } from '@/hooks/useSection'

export function SectionNamingDialog() {
    const { t } = useTranslation()
    const { showNamingDialog, pendingSection, closeNamingDialog, createSection } = useSection()
    const { fibers } = useFibers()
    const [name, setName] = useState('')

    useEffect(() => {
        if (showNamingDialog) {
            setName('')
        }
    }, [showNamingDialog])

    if (!showNamingDialog || !pendingSection) return null

    const fiber = fibers.find(f => f.id === pendingSection.fiberId)

    const handleSave = () => {
        if (name.trim()) {
            createSection(
                pendingSection.fiberId,
                pendingSection.startChannel,
                pendingSection.endChannel,
                name.trim()
            )
        }
        setName('')
        closeNamingDialog()
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleSave()
        } else if (e.key === 'Escape') {
            closeNamingDialog()
        }
    }

    return (
        <div
            className="absolute inset-0 bg-black/30 flex items-center justify-center z-[1001] pointer-events-auto"
            role="dialog"
            aria-modal="true"
            aria-labelledby="section-naming-title"
        >
            <div className="bg-white rounded-lg p-4 shadow-xl w-[calc(100%-2rem)] max-w-[300px]">
                <h3 id="section-naming-title" className="text-lg font-semibold mb-3 text-slate-800">{t('map.section.nameDialogTitle')}</h3>
                <div className="text-sm text-slate-500 mb-3">
                    <div>{`${t('common.fiber')}: `}{fiber?.name || pendingSection.fiberId}</div>
                    <div>{t('map.section.channels')} {pendingSection.startChannel} - {pendingSection.endChannel}</div>
                </div>
                <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={t('map.section.namePlaceholder')}
                    autoFocus
                    className="w-full border border-slate-300 rounded px-3 py-2 mb-3 min-h-[44px] focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <div className="flex justify-end gap-2">
                    <button
                        onClick={closeNamingDialog}
                        className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded min-h-[44px] flex items-center justify-center"
                    >
                        {t('common.cancel')}
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={!name.trim()}
                        className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
                    >
                        {t('common.save')}
                    </button>
                </div>
            </div>
        </div>
    )
}
