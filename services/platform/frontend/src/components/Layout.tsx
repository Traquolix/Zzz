import { useState, useRef, useEffect } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { LogOut, Menu, X } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { useAuth } from '@/hooks/useAuth'
import { usePermissions } from '@/hooks/usePermissions'
import { useBreadcrumbs } from '@/hooks/useBreadcrumbs'
import { Breadcrumb } from '@/components/ui/breadcrumb'
import { TechStatsHoverCard } from '@/components/TechStatsHoverCard'
import { ThemeToggle } from '@/components/ThemeToggle'
import { NotificationBell } from '@/components/NotificationBell'
import { useNotifications } from '@/hooks/useNotifications'
import { logger } from '@/lib/logger'
import { useRealtime } from '@/hooks/useRealtime'
import { PageTransition } from '@/components/PageTransition'
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
    const animationTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Track which item in this group was last visited (persists across navigation)
    const [lastVisitedPath, setLastVisitedPath] = useState<string | null>(null)

    // Check if current path matches this item or any alternate
    const allPaths = [item.path, ...visibleAlternates.map(a => a.path)]
    const isGroupActive = allPaths.some(p => location.pathname.toLowerCase() === p.toLowerCase())
    const currentMatchingPath = allPaths.find(p => location.pathname.toLowerCase() === p.toLowerCase())
    const primaryPath = currentMatchingPath || lastVisitedPath || item.path
    const isCurrentPath = location.pathname.toLowerCase() === primaryPath.toLowerCase()

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
            animationTimeoutRef.current = setTimeout(() => setIsOpen(false), 150)
        }, CLOSE_DELAY_MS)
    }

    useEffect(() => {
        return () => {
            if (openTimeoutRef.current) clearTimeout(openTimeoutRef.current)
            if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current)
            if (animationTimeoutRef.current) clearTimeout(animationTimeoutRef.current)
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
                aria-current={isCurrentPath ? 'page' : undefined}
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
                            aria-current={location.pathname.toLowerCase() === dropItem.path.toLowerCase() ? 'page' : undefined}
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
    const location = useLocation()
    const breadcrumbs = useBreadcrumbs()
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
    const mobileMenuRef = useRef<HTMLDivElement>(null)
    const {
        notifications,
        unreadCount,
        markAsRead,
        markAllRead,
        addNotification,
    } = useNotifications()
    const realtime = useRealtime()

    // Wire up WebSocket notifications from RealtimeProvider
    useEffect(() => {
        if (!realtime) return

        const unsubscribe = realtime.subscribe('incident', (data: unknown) => {
            try {
                const incident = data as {
                    type?: string
                    fiber?: string
                    fiberId?: string
                    id?: string
                    status?: string
                    prevStatus?: string
                }

                if (!incident) return

                // Handle new incident creation
                if (incident.type && incident.fiberId) {
                    addNotification({
                        ruleName: `New incident: ${incident.type}`,
                        fiberId: incident.fiberId,
                        channel: 0,
                        detail: `A new incident of type "${incident.type}" has been created.`,
                        timestamp: new Date().toISOString(),
                        read: false,
                    })
                }
                // Handle incident status change
                else if (incident.id && incident.status) {
                    addNotification({
                        ruleName: `Incident ${incident.id}`,
                        fiberId: incident.fiberId || 'unknown',
                        channel: 0,
                        detail: `Status changed to: ${incident.status}${
                            incident.prevStatus ? ` (from ${incident.prevStatus})` : ''
                        }`,
                        timestamp: new Date().toISOString(),
                        read: false,
                    })
                }
            } catch (error) {
                logger.error('Error processing incident notification:', error)
            }
        })

        return unsubscribe
    }, [realtime, addNotification])

    const handleLogout = async () => {
        await logout()
        navigate('/login')
    }

    // Close mobile menu when clicking outside
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (
                mobileMenuRef.current &&
                !mobileMenuRef.current.contains(event.target as Node)
            ) {
                setMobileMenuOpen(false)
            }
        }

        if (mobileMenuOpen) {
            document.addEventListener('mousedown', handleClickOutside)
            return () => {
                document.removeEventListener('mousedown', handleClickOutside)
            }
        }
    }, [mobileMenuOpen])

    const initial = username?.charAt(0).toUpperCase() || 'U'
    return (
        <div className="h-screen flex flex-col">
            <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:px-4 focus:py-2 focus:rounded focus-visible:ring-2 focus-visible:ring-blue-500"
            >
                {t('common.skipToContent')}
            </a>
            <header className="h-14 border-b border-slate-200 bg-white px-4 md:px-6 flex items-center justify-between">
                <div className="flex items-center gap-4 md:gap-8 flex-1 md:flex-none">
                    {/* Hamburger menu button - visible only on mobile */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="md:hidden"
                        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                        aria-label={t('common.menu') || 'Toggle menu'}
                        aria-expanded={mobileMenuOpen}
                    >
                        {mobileMenuOpen ? (
                            <X className="h-5 w-5" />
                        ) : (
                            <Menu className="h-5 w-5" />
                        )}
                    </Button>

                    <div className="flex items-center gap-2">
                        <span className="font-bold text-lg">{t('common.appTitle')}</span>
                        <TechStatsHoverCard>
                            <Badge className="cursor-default">{t('common.beta')}</Badge>
                        </TechStatsHoverCard>
                    </div>

                    {/* Desktop navigation - hidden on mobile */}
                    <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
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
                                    aria-current={location.pathname === item.path ? 'page' : undefined}
                                >
                                    {t(item.labelKey)}
                                </NavLink>
                            )
                        })}
                    </nav>
                </div>

                <div className="flex items-center gap-3">
                    <NotificationBell
                        notifications={notifications}
                        unreadCount={unreadCount}
                        onMarkAsRead={markAsRead}
                        onMarkAllRead={markAllRead}
                    />

                    <ThemeToggle />

                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm font-medium" aria-hidden="true">
                            {initial}
                        </div>
                        <span className="text-sm hidden sm:inline">{username}</span>
                    </div>

                    <Tooltip content={t('nav.logout', 'Log out')}>
                        <Button variant="ghost" size="icon" onClick={handleLogout} aria-label={t('auth.logout')}>
                            <LogOut className="h-4 w-4 text-gray-500" />
                        </Button>
                    </Tooltip>
                </div>
            </header>

            {/* Mobile navigation menu - visible on mobile when open */}
            {mobileMenuOpen && (
                <nav
                    ref={mobileMenuRef}
                    className="md:hidden bg-white border-b border-gray-200 overflow-y-auto"
                    aria-label="Mobile navigation"
                >
                    <div className="flex flex-col">
                        {visibleNavItems.map(item => {
                            // Filter alternates by permission
                            const visibleAlternates = (item.alternates || []).filter(
                                alt => !alt.requiredWidget || hasWidget(alt.requiredWidget)
                            )

                            // Regular nav link
                            return (
                                <div key={item.path}>
                                    <NavLink
                                        to={item.path}
                                        end={item.end}
                                        className={({ isActive }) =>
                                            `block px-4 py-3 font-medium text-sm border-b border-gray-100 transition-colors ${
                                                isActive
                                                    ? 'bg-blue-50 text-blue-600'
                                                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                                            }`
                                        }
                                        aria-current={location.pathname === item.path ? 'page' : undefined}
                                        onClick={() => setMobileMenuOpen(false)}
                                    >
                                        {t(item.labelKey)}
                                    </NavLink>

                                    {/* Alternates submenu */}
                                    {visibleAlternates.length > 0 && (
                                        <div className="bg-gray-50">
                                            {visibleAlternates.map(altItem => (
                                                <NavLink
                                                    key={altItem.path}
                                                    to={altItem.path}
                                                    className={({ isActive }) =>
                                                        `block px-6 py-2 text-sm border-b border-gray-100 transition-colors ${
                                                            isActive
                                                                ? 'bg-blue-100 text-blue-600'
                                                                : 'text-gray-600 hover:bg-gray-100'
                                                        }`
                                                    }
                                                    aria-current={location.pathname === altItem.path ? 'page' : undefined}
                                                    onClick={() => setMobileMenuOpen(false)}
                                                >
                                                    {t(altItem.labelKey)}
                                                </NavLink>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </nav>
            )}

            <Breadcrumb items={breadcrumbs} />

            <main className="flex-1 min-h-0 flex flex-col relative overflow-hidden bg-slate-50">
                <PageTransition />
            </main>
        </div>
    )
}
