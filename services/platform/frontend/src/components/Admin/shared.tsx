import { useTranslation } from 'react-i18next'

export function CheckboxGrid({
    items,
    selected,
    onChange,
    label,
}: {
    items: readonly { key: string; labelKey: string }[]
    selected: string[]
    onChange: (selected: string[]) => void
    label: string
}) {
    const { t } = useTranslation()
    const toggle = (key: string) => {
        onChange(selected.includes(key) ? selected.filter(k => k !== key) : [...selected, key])
    }
    return (
        <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">{label}</label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {items.map(item => (
                    <label key={item.key} className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={selected.includes(item.key)}
                            onChange={() => toggle(item.key)}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                        />
                        {t(item.labelKey)}
                    </label>
                ))}
            </div>
        </div>
    )
}

export function ActiveBadge({ isActive }: { isActive: boolean }) {
    return (
        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
            isActive ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
        }`}>
            {isActive ? 'Active' : 'Inactive'}
        </span>
    )
}
