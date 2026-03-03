import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Modal } from '@/components/ui/modal'
import { Button } from '@/components/ui/button'
import type { GenerateReportRequest } from '@/types/report'

const SECTION_OPTIONS = ['incidents', 'speed', 'volume'] as const

interface ReportFormProps {
    fibers: { id: string; name: string }[]
    generating: boolean
    onGenerate: (data: GenerateReportRequest) => void
    onClose: () => void
}

export function ReportForm({
    fibers,
    generating,
    onGenerate,
    onClose,
}: ReportFormProps) {
    const { t } = useTranslation()
    const [title, setTitle] = useState('')
    const [startTime, setStartTime] = useState('')
    const [endTime, setEndTime] = useState('')
    const [selectedFibers, setSelectedFibers] = useState<string[]>(fibers.map(f => f.id))
    const [selectedSections, setSelectedSections] = useState<string[]>([...SECTION_OPTIONS])
    const [recipientInput, setRecipientInput] = useState('')

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        const recipients = recipientInput
            .split(',')
            .map(s => s.trim())
            .filter(Boolean)

        onGenerate({
            title,
            startTime: new Date(startTime).toISOString(),
            endTime: new Date(endTime).toISOString(),
            fiberIds: selectedFibers,
            sections: selectedSections,
            recipients,
        })
    }

    const toggleFiber = (id: string) => {
        setSelectedFibers(prev =>
            prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
        )
    }

    const toggleSection = (section: string) => {
        setSelectedSections(prev =>
            prev.includes(section) ? prev.filter(s => s !== section) : [...prev, section]
        )
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-lg">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('reports.generateTitle')}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{t('reports.titleLabel')}</label>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            required
                            className="w-full border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder={t('reports.titlePlaceholder')}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{t('reports.startTime')}</label>
                            <input
                                type="datetime-local"
                                value={startTime}
                                onChange={(e) => setStartTime(e.target.value)}
                                required
                                className="w-full border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{t('reports.endTime')}</label>
                            <input
                                type="datetime-local"
                                value={endTime}
                                onChange={(e) => setEndTime(e.target.value)}
                                required
                                className="w-full border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{t('reports.fibers')}</label>
                        <div className="flex flex-wrap gap-2">
                            {fibers.map(fiber => (
                                <button
                                    key={fiber.id}
                                    type="button"
                                    onClick={() => toggleFiber(fiber.id)}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                                        selectedFibers.includes(fiber.id)
                                            ? 'bg-blue-100 border-blue-300 text-blue-700'
                                            : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-500'
                                    }`}
                                >
                                    {fiber.name || fiber.id}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{t('reports.sections')}</label>
                        <div className="flex flex-wrap gap-2">
                            {SECTION_OPTIONS.map(section => (
                                <button
                                    key={section}
                                    type="button"
                                    onClick={() => toggleSection(section)}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                                        selectedSections.includes(section)
                                            ? 'bg-blue-100 border-blue-300 text-blue-700'
                                            : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-500'
                                    }`}
                                >
                                    {t(`reports.sectionLabels.${section}`)}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{t('reports.recipients')}</label>
                        <input
                            type="text"
                            value={recipientInput}
                            onChange={(e) => setRecipientInput(e.target.value)}
                            className="w-full border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder={t('reports.recipientsPlaceholder')}
                        />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
                        >
                            {t('common.cancel')}
                        </button>
                        <Button
                            type="submit"
                            disabled={!title || !startTime || !endTime || selectedFibers.length === 0 || selectedSections.length === 0}
                            isLoading={generating}
                            loadingText={t('common.loading')}
                        >
                            {t('reports.generate')}
                        </Button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}
