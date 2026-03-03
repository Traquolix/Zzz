import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useNotifications } from './useNotifications'

describe('useNotifications', () => {
    it('initializes with empty notifications', () => {
        const { result } = renderHook(() => useNotifications())
        expect(result.current.notifications).toEqual([])
        expect(result.current.unreadCount).toBe(0)
    })

    it('addNotification adds a notification to the list', () => {
        const { result } = renderHook(() => useNotifications())

        act(() => {
            result.current.addNotification({
                ruleName: 'Rule 1',
                fiberId: 'fiber-1',
                channel: 5,
                detail: 'Test detail',
                timestamp: new Date().toISOString(),
                read: false,
            })
        })

        expect(result.current.notifications).toHaveLength(1)
        expect(result.current.notifications[0].ruleName).toBe('Rule 1')
        expect(result.current.notifications[0].fiberId).toBe('fiber-1')
        expect(result.current.unreadCount).toBe(1)
    })

    it('markAsRead marks a specific notification as read', () => {
        const { result } = renderHook(() => useNotifications())

        let id: string = ''
        act(() => {
            id = result.current.addNotification({
                ruleName: 'Rule 1',
                fiberId: 'fiber-1',
                channel: 5,
                detail: 'Test detail',
                timestamp: new Date().toISOString(),
                read: false,
            })
        })

        expect(result.current.unreadCount).toBe(1)

        act(() => {
            result.current.markAsRead(id)
        })

        expect(result.current.unreadCount).toBe(0)
        expect(result.current.notifications[0].read).toBe(true)
    })

    it('markAllRead marks all notifications as read', () => {
        const { result } = renderHook(() => useNotifications())

        act(() => {
            result.current.addNotification({
                ruleName: 'Rule 1',
                fiberId: 'fiber-1',
                channel: 5,
                detail: 'Test detail 1',
                timestamp: new Date().toISOString(),
                read: false,
            })
            result.current.addNotification({
                ruleName: 'Rule 2',
                fiberId: 'fiber-2',
                channel: 10,
                detail: 'Test detail 2',
                timestamp: new Date().toISOString(),
                read: false,
            })
        })

        expect(result.current.unreadCount).toBe(2)

        act(() => {
            result.current.markAllRead()
        })

        expect(result.current.unreadCount).toBe(0)
        expect(result.current.notifications.every(n => n.read)).toBe(true)
    })

    it('maintains max 50 notifications, dropping oldest', () => {
        const { result } = renderHook(() => useNotifications())

        act(() => {
            for (let i = 0; i < 60; i++) {
                result.current.addNotification({
                    ruleName: `Rule ${i}`,
                    fiberId: `fiber-${i}`,
                    channel: i,
                    detail: `Detail ${i}`,
                    timestamp: new Date().toISOString(),
                    read: false,
                })
            }
        })

        expect(result.current.notifications).toHaveLength(50)
        // Most recent should be at index 0
        expect(result.current.notifications[0].ruleName).toBe('Rule 59')
        // Oldest kept should be at index 49 (Rule 10, since 0-9 were dropped)
        expect(result.current.notifications[49].ruleName).toBe('Rule 10')
    })

    it('returns unique IDs for each notification', () => {
        const { result } = renderHook(() => useNotifications())

        const ids: string[] = []
        act(() => {
            for (let i = 0; i < 5; i++) {
                const id = result.current.addNotification({
                    ruleName: `Rule ${i}`,
                    fiberId: `fiber-${i}`,
                    channel: i,
                    detail: `Detail ${i}`,
                    timestamp: new Date().toISOString(),
                    read: false,
                })
                ids.push(id)
            }
        })

        const uniqueIds = new Set(ids)
        expect(uniqueIds.size).toBe(5)
    })
})
