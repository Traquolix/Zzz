import { useState, useRef, useEffect } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { LogOut } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { usePermissions } from '@/hooks/usePermissions'
import { TechStatsHoverCard } from '@/components/TechStatsHoverCard'
import type { NavItem } from '@/constants/navigation'

const HOVER_DELAY_MS = 400
const CLOSE_DELAY_MS = 150

type NavItemWithDropdownProps = {
    item: NavItem
    visibleAlternates: NavItem[]
    t: (key: string) => string
}

function NavItemWithDropdown({ item, visibleAlternates, t }: NavItemWithDropdownProps) {
    const [isOpen, setIsOpen] = useState(false)
    const [isVisible, setIsVisible] = useState(false)
    const containerRef = useRef<HTMLDivElement>(null)
    const location = useLocation()
    const openTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Track which item in this group was last visited (persists across navigation)
    const [lastVisitedPath, setLastVisitedPath] = useState<string | null>(null)

    // Check if current path matches this item or any alternate
    const allPaths = [item.path, ...visibleAlternates.map(a => a.path)]
    const isGroupActive = allPaths.some(p => location.pathname.toLowerCase() === p.toLowerCase())
    const currentMatchingPath = allPaths.find(p => location.pathname.toLowerCase() === p.toLowerCase())

    // Update last visited when we're on a path in this group
    useEffect(() => {
        if (currentMatchingPath) {
            setLastVisitedPath(currentMatchingPath)
        }
    }, [currentMatchingPath])

    // Determine which item to show as "primary":
    // 1. If currently on a path in this group, show that one
    // 2. Otherwise, show the last visited path in this group
    // 3. Fall back to the main item
    const primaryPath = currentMatchingPath || lastVisitedPath || item.path
    const primaryItem = primaryPath === item.path
        ? item
        : visibleAlternates.find(a => a.path.toLowerCase() === primaryPath.toLowerCase()) || item
    const dropdownItems = [item, ...visibleAlternates].filter(i => i.path !== primaryItem.path)

    const handleMouseEnter = () => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current)
            closeTimeoutRef.current = null
        }
        if (!isOpen) {
            openTimeoutRef.current = setTimeout(() => {
                setIsOpen(true)
                // Small delay before making visible for animation
                requestAnimationFrame(() => setIsVisible(true))
            }, HOVER_DELAY_MS)
        }
    }

    const handleMouseLeave = () => {
        if (openTimeoutRef.current) {
            clearTimeout(openTimeoutRef.current)
            openTimeoutRef.current = null
        }
        closeTimeoutRef.current = setTimeout(() => {
            setIsVisible(false)
            // Wait for animation to complete before removing from DOM
            setTimeout(() => setIsOpen(false), 150)
        }, CLOSE_DELAY_MS)
    }

    useEffect(() => {
        return () => {
            if (openTimeoutRef.current) clearTimeout(openTimeoutRef.current)
            if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current)
        }
    }, [])

    return (
        <div
            ref={containerRef}
            className="relative"
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
        >
            <NavLink
                to={primaryItem.path}
                end={primaryItem.end}
                className={`px-4 py-1.5 rounded-md font-medium text-sm transition-colors ${
                    isGroupActive
                        ? 'bg-blue-50 text-blue-600'
                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
            >
                {t(primaryItem.labelKey)}
            </NavLink>

            {isOpen && dropdownItems.length > 0 && (
                <div
                    className={`absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg py-1 z-50 transition-all duration-150 ease-out ${
                        isVisible
                            ? 'opacity-100 translate-y-0'
                            : 'opacity-0 -translate-y-1'
                    }`}
                >
                    {dropdownItems.map(dropItem => (
                        <NavLink
                            key={dropItem.path}
                            to={dropItem.path}
                            className={({ isActive }) =>
                                `block px-4 py-2 text-sm whitespace-nowrap transition-colors ${
                                    isActive
                                        ? 'bg-blue-50 text-blue-600'
                                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                                }`
                            }
                            onClick={() => {
                                setIsVisible(false)
                                setTimeout(() => setIsOpen(false), 150)
                            }}
                        >
                            {t(dropItem.labelKey)}
                        </NavLink>
                    ))}
                </div>
            )}
        </div>
    )
}

export function Layout() {
    const { username, logout } = useAuth()
    const { visibleNavItems, hasWidget } = usePermissions()
    const navigate = useNavigate()
    const { t } = useTranslation()

    const handleLogout = async () => {
        await logout()
        navigate('/login')
    }

    const initial = username?.charAt(0).toUpperCase() || 'U'
    return (
        <div className="h-screen flex flex-col">
            <header className="h-14 border-b bg-white px-6 flex items-center justify-between">
                <div className="flex items-center gap-8">
                    <div className="flex items-center gap-2">
                        <span className="font-bold text-lg">{t('common.appTitle')}</span>
                        <TechStatsHoverCard>
                            <Badge className="cursor-default">{t('common.beta')}</Badge>
                        </TechStatsHoverCard>
                    </div>

                    <nav className="flex items-center gap-1" aria-label="Main navigation">
                        {visibleNavItems.map(item => {
                            // Filter alternates by permission
                            const visibleAlternates = (item.alternates || []).filter(
                                alt => !alt.requiredWidget || hasWidget(alt.requiredWidget)
                            )

                            // If item has visible alternates, render dropdown
                            if (visibleAlternates.length > 0) {
                                return (
                                    <NavItemWithDropdown
                                        key={item.path}
                                        item={item}
                                        visibleAlternates={visibleAlternates}
                                        t={t}
                                    />
                                )
                            }

                            // Regular nav link
                            return (
                                <NavLink
                                    key={item.path}
                                    to={item.path}
                                    end={item.end}
                                    className={({ isActive }) =>
                                        `px-4 py-1.5 rounded-md font-medium text-sm transition-colors ${
                                            isActive
                                                ? 'bg-blue-50 text-blue-600'
                                                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                                        }`
                                    }
                                >
                                    {t(item.labelKey)}
                                </NavLink>
                            )
                        })}
                    </nav>
                </div>

                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm font-medium" aria-hidden="true">
                            {initial}
                        </div>
                        <span className="text-sm">{username}</span>
                    </div>

                    <Button variant="ghost" size="icon" onClick={handleLogout} aria-label={t('auth.logout')}>
                        <LogOut className="h-4 w-4 text-gray-500" />
                    </Button>
                </div>
            </header>

            <main className="flex-1 bg-slate-50 relative overflow-auto">
                <Outlet />
            </main>
        </div>
    )
}
