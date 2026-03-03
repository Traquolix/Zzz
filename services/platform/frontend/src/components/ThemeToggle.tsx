import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Sun, Palette } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'

const THEME_KEY = 'sequoia_theme'
const THEMES = ['light', 'sequoia'] as const
type Theme = (typeof THEMES)[number]

export function ThemeToggle() {
    const [theme, setTheme] = useState<Theme>(() => {
        const saved = localStorage.getItem(THEME_KEY)
        if (saved === 'sequoia') return 'sequoia'
        return 'light'
    })
    const { t } = useTranslation()

    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    useEffect(() => {
        document.documentElement.classList.remove('dark', 'sequoia')
        if (theme !== 'light') {
            document.documentElement.classList.add(theme)
        }
        localStorage.setItem(THEME_KEY, theme)
    }, [theme])

    useEffect(() => {
        return () => {
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current)
            }
        }
    }, [])

    const handleToggle = () => {
        const html = document.documentElement
        html.classList.add('theme-transitioning')
        setTheme(current => THEMES[(THEMES.indexOf(current) + 1) % THEMES.length])
        timeoutRef.current = setTimeout(() => {
            html.classList.remove('theme-transitioning')
        }, 300)
    }

    const tooltipKey =
        theme === 'light'
            ? t('theme.switchToSequoia', 'Switch to SequoIA theme')
            : t('theme.switchToLight', 'Switch to light mode')

    const ariaLabel =
        theme === 'light'
            ? 'Switch to SequoIA theme'
            : 'Switch to light mode'

    const Icon = theme === 'light' ? Palette : Sun

    return (
        <Tooltip content={tooltipKey}>
            <button
                onClick={handleToggle}
                className="p-2 rounded-md hover:bg-slate-200 transition-colors"
                aria-label={ariaLabel}
                type="button"
            >
                <Icon className="h-5 w-5" />
            </button>
        </Tooltip>
    )
}
