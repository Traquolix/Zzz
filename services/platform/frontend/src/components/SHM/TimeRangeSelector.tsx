import { useState } from 'react'
import { format, subDays, subHours, startOfDay, endOfDay } from 'date-fns'
import { Calendar as CalendarIcon } from 'lucide-react'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import type { DateRange } from 'react-day-picker'

type Preset = {
    label: string
    getValue: () => { from: Date; to: Date }
}

const PRESETS: Preset[] = [
    {
        label: '24h',
        getValue: () => ({ from: subHours(new Date(), 24), to: new Date() }),
    },
    {
        label: '7d',
        getValue: () => ({ from: subDays(new Date(), 7), to: new Date() }),
    },
    {
        label: '30d',
        getValue: () => ({ from: subDays(new Date(), 30), to: new Date() }),
    },
    {
        label: 'All',
        getValue: () => ({ from: new Date(0), to: new Date() }),
    },
]

type Props = {
    value: { from: Date; to: Date }
    onChange: (range: { from: Date; to: Date }) => void
    className?: string
}

export function TimeRangeSelector({ value, onChange, className }: Props) {
    const [isOpen, setIsOpen] = useState(false)
    const [activePreset, setActivePreset] = useState<string | null>('All')

    const handlePresetClick = (preset: Preset) => {
        setActivePreset(preset.label)
        onChange(preset.getValue())
    }

    const handleCalendarSelect = (range: DateRange | undefined) => {
        if (range?.from) {
            setActivePreset(null)
            onChange({
                from: startOfDay(range.from),
                to: range.to ? endOfDay(range.to) : endOfDay(range.from),
            })
        }
    }

    const formatRange = () => {
        if (activePreset === 'All') return 'All time'
        if (activePreset) return `Past ${activePreset}`
        return `${format(value.from, 'MMM d')} - ${format(value.to, 'MMM d, yyyy')}`
    }

    return (
        <div className={`flex items-center gap-2 ${className ?? ''}`}>
            {/* Preset buttons */}
            <div className="flex items-center gap-1">
                {PRESETS.map((preset) => (
                    <button
                        key={preset.label}
                        onClick={() => handlePresetClick(preset)}
                        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                            activePreset === preset.label
                                ? 'bg-blue-500 text-white'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                    >
                        {preset.label}
                    </button>
                ))}
            </div>

            {/* Custom date range picker */}
            <Popover open={isOpen} onOpenChange={setIsOpen}>
                <PopoverTrigger asChild>
                    <Button
                        variant="outline"
                        className={`h-8 px-3 text-xs font-normal ${
                            !activePreset ? 'border-blue-500 text-blue-600' : ''
                        }`}
                    >
                        <CalendarIcon className="mr-2 h-3.5 w-3.5" />
                        {formatRange()}
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="end">
                    <Calendar
                        mode="range"
                        defaultMonth={value.from}
                        selected={{ from: value.from, to: value.to }}
                        onSelect={handleCalendarSelect}
                        numberOfMonths={2}
                    />
                </PopoverContent>
            </Popover>
        </div>
    )
}
