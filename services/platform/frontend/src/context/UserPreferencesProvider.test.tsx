/**
 * Integration tests for UserPreferencesProvider.
 *
 * Verifies load-on-auth, functional setState for concurrent updates,
 * and consecutive failure toast logic.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { type ReactNode } from 'react'

// --- Mocks ---

const mockLoadPreferences = vi.fn()
const mockSavePreferences = vi.fn()
let mockIsAuthenticated = true
let mockAuthLoading = false

vi.mock('@/api/preferences', () => ({
    loadPreferences: (...args: any[]) => mockLoadPreferences(...args),
    savePreferences: (...args: any[]) => mockSavePreferences(...args),
}))

vi.mock('@/hooks/useAuth', () => ({
    useAuth: () => ({
        isAuthenticated: mockIsAuthenticated,
        isLoading: mockAuthLoading,
    }),
}))

vi.mock('sonner', () => ({
    toast: {
        error: vi.fn(),
        success: vi.fn(),
    },
}))

// Import after mocks
import { UserPreferencesProvider } from './UserPreferencesProvider'
import { UserPreferencesContext } from './UserPreferencesContext'
import { useContext } from 'react'
import { toast } from 'sonner'

function useTestPreferences() {
    return useContext(UserPreferencesContext)
}

function wrapper({ children }: { children: ReactNode }) {
    return <UserPreferencesProvider>{children}</UserPreferencesProvider>
}

// Helper to access result.current with non-null assertion
const getCurrent = (result: any) => result.current!

describe('UserPreferencesProvider', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockIsAuthenticated = true
        mockAuthLoading = false
        mockLoadPreferences.mockResolvedValue({ dashboard: {}, map: {} })
        mockSavePreferences.mockResolvedValue(undefined)
    })

    it('loads preferences on auth', async () => {
        const prefs = { dashboard: { layouts: {} }, map: {} }
        mockLoadPreferences.mockResolvedValueOnce(prefs)

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })

        expect(mockLoadPreferences).toHaveBeenCalledOnce()
        expect(getCurrent(result).preferences).toEqual(prefs)
    })

    it('updatePreferences uses functional setState (no clobber)', async () => {
        mockLoadPreferences.mockResolvedValueOnce({ dashboard: { a: 1 }, map: { b: 2 } })

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })

        // Two rapid partial updates
        await act(async () => {
            await getCurrent(result).updatePreferences({ dashboard: { a: 10 } } as any)
        })
        await act(async () => {
            await getCurrent(result).updatePreferences({ map: { b: 20 } } as any)
        })

        // Both updates should be reflected
        expect(getCurrent(result).preferences?.dashboard).toEqual({ a: 10 })
        expect(getCurrent(result).preferences?.map).toEqual({ b: 20 })
    })

    it('shows toast only after 2 consecutive failures', async () => {
        mockLoadPreferences.mockResolvedValueOnce({ dashboard: {}, map: {} })
        mockSavePreferences.mockRejectedValue(new Error('network'))

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })

        // First failure — silent
        await act(async () => {
            await getCurrent(result).savePreferences({ dashboard: {}, map: {} })
        })
        expect(toast.error).not.toHaveBeenCalled()

        // Second failure — toast shown
        await act(async () => {
            await getCurrent(result).savePreferences({ dashboard: {}, map: {} })
        })
        expect(toast.error).toHaveBeenCalledOnce()
    })

    it('resets failure counter on success', async () => {
        mockLoadPreferences.mockResolvedValueOnce({ dashboard: {}, map: {} })

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })

        // Fail once
        mockSavePreferences.mockRejectedValueOnce(new Error('fail'))
        await act(async () => {
            await getCurrent(result).savePreferences({ dashboard: {}, map: {} })
        })

        // Succeed (resets counter)
        mockSavePreferences.mockResolvedValueOnce(undefined)
        await act(async () => {
            await getCurrent(result).savePreferences({ dashboard: {}, map: {} })
        })

        // Fail again — should be counted as first failure again (no toast)
        mockSavePreferences.mockRejectedValueOnce(new Error('fail'))
        await act(async () => {
            await getCurrent(result).savePreferences({ dashboard: {}, map: {} })
        })

        // Should not have toast (only 1 consecutive failure after reset)
        expect(toast.error).not.toHaveBeenCalled()
    })

    it('reverts preferences on save error', async () => {
        const original = { dashboard: { saved: true }, map: {} }
        mockLoadPreferences.mockResolvedValueOnce(original)
        mockSavePreferences.mockRejectedValue(new Error('network'))

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })
        expect(getCurrent(result).preferences).toEqual(original)

        // Attempt save with new prefs — should optimistically update then revert
        const attempted = { dashboard: { saved: false }, map: { changed: true } }
        await act(async () => {
            await getCurrent(result).savePreferences(attempted as any)
        })

        // After error, preferences should revert to original
        expect(getCurrent(result).preferences).toEqual(original)
    })

    it('keeps new preferences on successful save', async () => {
        const original = { dashboard: { v: 1 }, map: {} }
        mockLoadPreferences.mockResolvedValueOnce(original)
        mockSavePreferences.mockResolvedValue(undefined)

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })

        const updated = { dashboard: { v: 2 }, map: { new: true } }
        await act(async () => {
            await getCurrent(result).savePreferences(updated as any)
        })

        expect(getCurrent(result).preferences).toEqual(updated)
    })

    it('does not load preferences when not authenticated', async () => {
        mockIsAuthenticated = false

        const { result } = renderHook(useTestPreferences, { wrapper })

        await waitFor(() => {
            expect(getCurrent(result).isLoading).toBe(false)
        })

        expect(mockLoadPreferences).not.toHaveBeenCalled()
        expect(getCurrent(result).preferences).toBeNull()
    })
})
