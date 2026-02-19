import { useState, useMemo } from 'react'
import { ChevronDown, Calendar } from 'lucide-react'
import { format, startOfDay, endOfDay, eachDayOfInterval, isSameDay } from 'date-fns'

type Props = {
    dataStart: Date
    dataEnd: Date
    selectedDay: Date | null
    onSelectDay: (day: Date | null) => void
}

export function DaySelector({ dataStart, dataEnd, selectedDay, onSelectDay }: Props) {
    const [isOpen, setIsOpen] = useState(false)

    // Generate list of available days
    const availableDays = useMemo(() => {
        return eachDayOfInterval({ start: startOfDay(dataStart), end: startOfDay(dataEnd) }).reverse()
    }, [dataStart, dataEnd])

    const selectedLabel = selectedDay
        ? format(selectedDay, 'MMM d, yyyy')
        : 'All time'

    const handleSelect = (day: Date | null) => {
        onSelectDay(day)
        setIsOpen(false)
    }

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
            >
                <Calendar className="w-4 h-4 text-slate-400" />
                <span>{selectedLabel}</span>
                <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <>
                    <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
                    <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-20 min-w-[180px] max-h-[300px] overflow-auto">
                        <button
                            onClick={() => handleSelect(null)}
                            className={`block w-full text-left px-4 py-2 text-sm hover:bg-slate-50 ${
                                selectedDay === null ? 'bg-blue-50 text-blue-600' : 'text-slate-700'
                            }`}
                        >
                            All time
                        </button>
                        <div className="border-t border-slate-100 my-1" />
                        {availableDays.map((day) => {
                            const isSelected = selectedDay && isSameDay(day, selectedDay)
                            return (
                                <button
                                    key={day.toISOString()}
                                    onClick={() => handleSelect(day)}
                                    className={`block w-full text-left px-4 py-2 text-sm hover:bg-slate-50 ${
                                        isSelected ? 'bg-blue-50 text-blue-600' : 'text-slate-700'
                                    }`}
                                >
                                    {format(day, 'EEE, MMM d, yyyy')}
                                </button>
                            )
                        })}
                    </div>
                </>
            )}
        </div>
    )
}

/**
 * Get time range for a selected day (start and end of day)
 */
export function getDayTimeRange(day: Date | null): { from: Date; to: Date } | null {
    if (!day) return null
    return {
        from: startOfDay(day),
        to: endOfDay(day),
    }
}
