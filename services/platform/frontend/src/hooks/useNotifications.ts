import { useState, useCallback, useMemo } from 'react'

export interface Notification {
    id: string
    ruleName: string
    fiberId: string
    channel: number
    detail: string
    timestamp: string
    read: boolean
}

const MAX_NOTIFICATIONS = 50

export function useNotifications() {
    const [notifications, setNotifications] = useState<Notification[]>([])

    const unreadCount = useMemo(() => {
        return notifications.filter(n => !n.read).length
    }, [notifications])

    const markAsRead = useCallback((id: string) => {
        setNotifications(prev =>
            prev.map(n =>
                n.id === id ? { ...n, read: true } : n
            )
        )
    }, [])

    const markAllRead = useCallback(() => {
        setNotifications(prev =>
            prev.map(n => ({ ...n, read: true }))
        )
    }, [])

    const addNotification = useCallback((data: Omit<Notification, 'id'>) => {
        const id = `notif-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        const newNotification: Notification = { ...data, id }

        setNotifications(prev => {
            const updated = [newNotification, ...prev]
            // Keep only the last MAX_NOTIFICATIONS
            return updated.slice(0, MAX_NOTIFICATIONS)
        })

        return id
    }, [])

    return {
        notifications,
        unreadCount,
        markAsRead,
        markAllRead,
        addNotification,
    }
}
