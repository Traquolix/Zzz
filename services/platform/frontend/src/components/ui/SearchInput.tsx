import { useState, useEffect, useRef } from 'react'
import { Search, X } from 'lucide-react'

const DEFAULT_DEBOUNCE_MS = 300

type SearchInputProps = {
    value: string
    onChange: (value: string) => void
    placeholder?: string
    className?: string
    debounceMs?: number
}

export function SearchInput({
    value,
    onChange,
    placeholder = 'Search...',
    className = '',
    debounceMs = DEFAULT_DEBOUNCE_MS,
}: SearchInputProps) {
    const [localValue, setLocalValue] = useState(value)
    const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Update local value when external value changes
    useEffect(() => {
        setLocalValue(value)
    }, [value])

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const newValue = e.currentTarget.value
        setLocalValue(newValue)

        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
        }

        debounceTimerRef.current = setTimeout(() => {
            onChange(newValue)
        }, debounceMs)
    }

    const handleClear = () => {
        setLocalValue('')
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
        }
        onChange('')
    }

    return (
        <div className={`relative ${className}`}>
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-slate-400 pointer-events-none" aria-hidden="true" />
            <input
                type="text"
                value={localValue}
                onChange={handleInputChange}
                placeholder={placeholder}
                className="w-full pl-10 pr-10 py-2 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white text-slate-900 placeholder-slate-500"
            />
            {localValue && (
                <button
                    onClick={handleClear}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 p-1 hover:bg-slate-100 rounded transition-colors"
                    aria-label="Clear search"
                    type="button"
                >
                    <X className="h-4 w-4 text-slate-400" />
                </button>
            )}
        </div>
    )
}
