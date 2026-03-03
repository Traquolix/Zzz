import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import type { Notification } from '@/hooks/useNotifications'

interface NotificationBellProps {
    notifications: Notification[]
    unreadCount: number
    onMarkAsRead: (id: string) => void
    onMarkAllRead: () => void
}

function formatTime(timestamp: string): string {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`

    return date.toLocaleDateString()
}

export function NotificationBell({
    notifications,
    unreadCount,
    onMarkAsRead,
    onMarkAllRead,
}: NotificationBellProps) {
    const [isOpen, setIsOpen] = useState(false)
    const dropdownRef = useRef<HTMLDivElement>(null)
    const buttonRef = useRef<HTMLButtonElement>(null)
    const { t } = useTranslation()

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (
                dropdownRef.current &&
                buttonRef.current &&
                !dropdownRef.current.contains(event.target as Node) &&
                !buttonRef.current.contains(event.target as Node)
            ) {
                setIsOpen(false)
            }
        }

        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside)
            return () => {
                document.removeEventListener('mousedown', handleClickOutside)
            }
        }
    }, [isOpen])

    // Mark all notifications as read when dropdown is opened
    useEffect(() => {
        if (isOpen && unreadCount > 0) {
            onMarkAllRead()
        }
    }, [isOpen, unreadCount, onMarkAllRead])

    return (
        <div className="relative">
            <span role="status" aria-live="polite" className="sr-only">
                {unreadCount > 0
                    ? t('notifications.unreadCount', { count: unreadCount })
                    : t('notifications.noNotifications')
                }
            </span>

            <Tooltip content={t('notifications.title', 'Notifications')}>
                <Button
                    ref={buttonRef}
                    variant="ghost"
                    size="icon"
                    onClick={() => setIsOpen(!isOpen)}
                    aria-label={t('notifications.aria', { count: unreadCount })}
                    className="relative"
                >
                    <Bell className="h-4 w-4 text-gray-500" />
                    {unreadCount > 0 && (
                        <div className="absolute -top-1 -right-1 h-5 w-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
                            {unreadCount > 9 ? '9+' : unreadCount}
                        </div>
                    )}
                </Button>
            </Tooltip>

            {isOpen && (
                <div
                    ref={dropdownRef}
                    className="absolute top-full right-0 mt-2 w-80 bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg shadow-lg z-50"
                >
                    <div className="border-b border-gray-200 dark:border-slate-700 p-4 flex items-center justify-between">
                        <h3 className="font-semibold text-gray-900 dark:text-slate-100">
                            {t('notifications.title')}
                        </h3>
                        {unreadCount > 0 && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                    onMarkAllRead()
                                }}
                                className="text-xs"
                            >
                                {t('notifications.markAllRead')}
                            </Button>
                        )}
                    </div>

                    <div className="max-h-96 overflow-y-auto">
                        {notifications.length === 0 ? (
                            <div className="p-4 text-center text-sm text-gray-500 dark:text-slate-400">
                                {t('notifications.noNotifications')}
                            </div>
                        ) : (
                            <ul className="divide-y divide-gray-100 dark:divide-slate-800">
                                {notifications.map(notification => (
                                    <li
                                        key={notification.id}
                                        className={`p-4 hover:bg-gray-50 dark:hover:bg-slate-800 cursor-pointer transition-colors ${
                                            !notification.read
                                                ? 'bg-blue-50 dark:bg-slate-800'
                                                : ''
                                        }`}
                                        onClick={() => {
                                            if (!notification.read) {
                                                onMarkAsRead(notification.id)
                                            }
                                        }}
                                    >
                                        <div className="flex items-start justify-between">
                                            <div className="flex-1">
                                                <p className="font-medium text-sm text-gray-900 dark:text-slate-100">
                                                    {notification.ruleName}
                                                </p>
                                                <p className="text-xs text-gray-600 dark:text-slate-400 mt-1">
                                                    {t('common.fiber')}:{' '}
                                                    {notification.fiberId}
                                                    {' | '}
                                                    {t('common.channel')}:{' '}
                                                    {notification.channel}
                                                </p>
                                                <p className="text-xs text-gray-500 dark:text-slate-500 mt-1">
                                                    {notification.detail}
                                                </p>
                                            </div>
                                            {!notification.read && (
                                                <div className="ml-2 h-2 w-2 bg-blue-500 rounded-full flex-shrink-0 mt-1" />
                                            )}
                                        </div>
                                        <p className="text-xs text-gray-400 dark:text-slate-500 mt-2">
                                            {formatTime(
                                                notification.timestamp
                                            )}
                                        </p>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
