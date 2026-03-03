/**
 * Tests for usePreferenceMap hook.
 *
 * Verifies:
 * 1. Initial state is empty Map before preferences load
 * 2. Map populates from preferences after load
 * 3. scheduleSave triggers debounced updatePreferences
 * 4. Double-init protection (only loads once)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

// --- Mocks ---

const mockUpdatePreferences = vi.fn()
let mockPreferences: Record<string, any> | null = null
let mockPrefsLoading = true

vi.mock('@/hooks/useUserPreferences', () => ({
    useUserPreferences: () => ({
        preferences: mockPreferences,
        updatePreferences: mockUpdatePreferences,
        isLoading: mockPrefsLoading,
    }),
}))

vi.mock('@/hooks/useDebouncedSync', () => ({
    useDebouncedSync: (fn: any) => fn, // pass-through, no actual debounce in tests
}))

// Import after mocks
import { usePreferenceMap } from './usePreferenceMap'

// --- Test config ---

type TestItem = { name: string; value: number }

const testConfig = {
    load: (prefs: any) => {
        const items = prefs?.testItems as TestItem[] | undefined
        if (!items) return null
        return new Map(items.map(i => [i.name, i]))
    },
    save: (map: Map<string, TestItem>, currentPrefs: any) => ({
        ...currentPrefs,
        testItems: Array.from(map.values()),
    }),
}

describe('usePreferenceMap', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockPreferences = null
        mockPrefsLoading = true
    })

    it('starts with empty Map while preferences are loading', () => {
        const { result } = renderHook(() => usePreferenceMap(testConfig))
        expect(result.current.map.size).toBe(0)
        expect(result.current.isLoading).toBe(true)
    })

    it('loads from preferences when they become available', async () => {
        mockPrefsLoading = true
        mockPreferences = null

        const { result, rerender } = renderHook(() => usePreferenceMap(testConfig))
        expect(result.current.map.size).toBe(0)

        // Simulate preferences finishing load
        mockPrefsLoading = false
        mockPreferences = {
            testItems: [
                { name: 'alpha', value: 1 },
                { name: 'beta', value: 2 },
            ],
        }
        rerender()

        await waitFor(() => {
            expect(result.current.map.size).toBe(2)
        })
        expect(result.current.map.get('alpha')).toEqual({ name: 'alpha', value: 1 })
    })

    it('scheduleSave calls updatePreferences with serialized Map', () => {
        mockPrefsLoading = false
        mockPreferences = { testItems: [] }

        const { result } = renderHook(() => usePreferenceMap(testConfig))

        const newMap = new Map<string, TestItem>([
            ['gamma', { name: 'gamma', value: 3 }],
        ])

        act(() => {
            result.current.scheduleSave(newMap)
        })

        expect(mockUpdatePreferences).toHaveBeenCalledWith(
            expect.objectContaining({
                testItems: [{ name: 'gamma', value: 3 }],
            })
        )
    })

    it('only initializes once even with multiple rerenders', async () => {
        mockPrefsLoading = false
        mockPreferences = {
            testItems: [{ name: 'first', value: 1 }],
        }

        const { result, rerender } = renderHook(() => usePreferenceMap(testConfig))

        await waitFor(() => {
            expect(result.current.map.size).toBe(1)
        })

        // Change underlying preferences data
        mockPreferences = {
            testItems: [{ name: 'second', value: 2 }, { name: 'third', value: 3 }],
        }
        rerender()

        // Should still have original data — not re-initialized
        expect(result.current.map.size).toBe(1)
        expect(result.current.map.get('first')).toEqual({ name: 'first', value: 1 })
    })
})
