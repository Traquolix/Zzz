import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { Layouts } from '@/types/dashboard'

// Simple mock setup
vi.mock('./useUserPreferences')
vi.mock('./usePermissions')

import { useDashboard } from './useDashboard'
import { useUserPreferences } from './useUserPreferences'
import { usePermissions } from './usePermissions'

describe('useDashboard', () => {
    beforeEach(() => {
        vi.clearAllMocks()

        // Default mock implementations
        vi.mocked(useUserPreferences).mockReturnValue({
            preferences: {
                dashboard: {
                    widgets: ['map', 'traffic_monitor'],
                    layouts: {
                        lg: [
                            { i: 'map', x: 0, y: 0, w: 5, h: 11 },
                            { i: 'traffic_monitor', x: 5, y: 0, w: 4, h: 7 },
                        ],
                    },
                },
            },
            updatePreferences: vi.fn(),
            isLoading: false,
        } as any)

        vi.mocked(usePermissions).mockReturnValue({
            allowedWidgets: ['map', 'traffic_monitor', 'incidents', 'shm'],
            allowedLayers: [],
            hasWidget: vi.fn((w) => ['map', 'traffic_monitor', 'incidents', 'shm'].includes(w)),
            hasLayer: vi.fn(),
            canAccessPage: vi.fn(),
            visibleNavItems: [],
        } as any)
    })

    it('should initialize with saved preferences', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        expect(result.current.widgets).toHaveLength(2)
        expect(result.current.widgets[0].id).toBe('map')
        expect(result.current.widgets[1].id).toBe('traffic_monitor')
    })

    it('should filter widgets by permissions', async () => {
        vi.mocked(usePermissions).mockReturnValue({
            allowedWidgets: ['map', 'incidents'],
            allowedLayers: [],
            hasWidget: vi.fn((w) => ['map', 'incidents'].includes(w)),
            hasLayer: vi.fn(),
            canAccessPage: vi.fn(),
            visibleNavItems: [],
        } as any)

        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        // Should only have 'map' from the saved preferences list since 'traffic_monitor' is not in allowedWidgets
        expect(result.current.widgets).toHaveLength(1)
        expect(result.current.widgets[0].id).toBe('map')
    })

    it('should initialize with saved layouts', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        expect(result.current.layouts.lg).toBeDefined()
    })

    it('should start with editMode false', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        expect(result.current.editMode).toBe(false)
    })

    it('should toggle editMode on/off', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        expect(result.current.editMode).toBe(false)

        act(() => {
            result.current.toggleEditMode()
        })

        expect(result.current.editMode).toBe(true)

        act(() => {
            result.current.toggleEditMode()
        })

        expect(result.current.editMode).toBe(false)
    })

    it('should save preferences when exiting edit mode', async () => {
        const updatePreferences = vi.fn()
        vi.mocked(useUserPreferences).mockReturnValue({
            preferences: {
                dashboard: {
                    widgets: ['map', 'traffic_monitor'],
                    layouts: {
                        lg: [
                            { i: 'map', x: 0, y: 0, w: 5, h: 11 },
                            { i: 'traffic_monitor', x: 5, y: 0, w: 4, h: 7 },
                        ],
                    },
                },
            },
            updatePreferences,
            isLoading: false,
        } as any)

        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        act(() => {
            result.current.toggleEditMode()
        })

        expect(result.current.editMode).toBe(true)
        expect(updatePreferences).not.toHaveBeenCalled()

        act(() => {
            result.current.toggleEditMode()
        })

        expect(updatePreferences).toHaveBeenCalled()
        expect(result.current.editMode).toBe(false)
    })

    it('should add widget with correct type', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        const initialLength = result.current.widgets.length

        act(() => {
            result.current.addWidget('shm')
        })

        expect(result.current.widgets).toHaveLength(initialLength + 1)
        const newWidget = result.current.widgets[result.current.widgets.length - 1]
        expect(newWidget.id).toMatch(/^shm-\d+$/)
    })

    it('should not add widget if not allowed by permissions', async () => {
        vi.mocked(usePermissions).mockReturnValue({
            allowedWidgets: ['map'],
            allowedLayers: [],
            hasWidget: vi.fn((w) => w === 'map'),
            hasLayer: vi.fn(),
            canAccessPage: vi.fn(),
            visibleNavItems: [],
        } as any)

        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        const initialLength = result.current.widgets.length

        act(() => {
            result.current.addWidget('incidents')
        })

        expect(result.current.widgets).toHaveLength(initialLength)
    })

    it('should add widget to breakpoint layouts', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        act(() => {
            result.current.addWidget('shm')
        })

        const newWidgetId = result.current.widgets[result.current.widgets.length - 1].id

        // Check that the widget was added to lg layout (which is defined in mock)
        expect(result.current.layouts.lg?.some((item) => item.i === newWidgetId)).toBe(true)
    })

    it('should delete widget by id', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        const widgetToDelete = result.current.widgets[0].id
        const initialLength = result.current.widgets.length

        act(() => {
            result.current.deleteWidget(widgetToDelete)
        })

        expect(result.current.widgets).toHaveLength(initialLength - 1)
        expect(result.current.widgets.some((w) => w.id === widgetToDelete)).toBe(false)
    })

    it('should remove widget from breakpoint layouts when deleted', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        const widgetToDelete = result.current.widgets[0].id

        act(() => {
            result.current.deleteWidget(widgetToDelete)
        })

        // Check that the widget was removed from lg layout (which is defined in mock)
        expect(result.current.layouts.lg?.some((item) => item.i === widgetToDelete)).toBe(false)
    })

    it('should handle layout changes', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        const newLayouts: Layouts = {
            lg: [
                { i: 'map', x: 0, y: 0, w: 6, h: 12 },
                { i: 'traffic_monitor', x: 6, y: 0, w: 6, h: 7 },
            ],
            md: [],
            sm: [],
            xs: [],
        }

        act(() => {
            result.current.handleLayoutChange(newLayouts.lg!, newLayouts)
        })

        expect(result.current.layouts.lg).toEqual(newLayouts.lg)
    })

    it('should return isLoading false after initialization completes', async () => {
        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        expect(result.current.isLoading).toBe(false)
    })

    it('should update preferences when layout changes and in edit mode', async () => {
        const updatePreferences = vi.fn()
        vi.mocked(useUserPreferences).mockReturnValue({
            preferences: {
                dashboard: {
                    widgets: ['map', 'traffic_monitor'],
                    layouts: {
                        lg: [
                            { i: 'map', x: 0, y: 0, w: 5, h: 11 },
                            { i: 'traffic_monitor', x: 5, y: 0, w: 4, h: 7 },
                        ],
                    },
                },
            },
            updatePreferences,
            isLoading: false,
        } as any)

        const { result } = renderHook(() => useDashboard())

        await act(async () => {
            // Wait for initialization effect
        })

        act(() => {
            result.current.toggleEditMode()
        })

        const newLayouts: Layouts = {
            lg: [{ i: 'map', x: 0, y: 0, w: 6, h: 12 }],
            md: [],
            sm: [],
            xs: [],
        }

        act(() => {
            result.current.handleLayoutChange(newLayouts.lg!, newLayouts)
            result.current.toggleEditMode()
        })

        expect(updatePreferences).toHaveBeenCalled()
    })
})
