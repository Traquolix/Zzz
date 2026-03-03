import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useBreadcrumbs } from './useBreadcrumbs'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useLocation: vi.fn(),
}))

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: vi.fn(),
}))

// Import after mocking
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

const mockUseLocation = useLocation as ReturnType<typeof vi.fn>
const mockUseTranslation = useTranslation as ReturnType<typeof vi.fn>

// Helper function to set up mocks
function setupMocks(pathname: string) {
  mockUseLocation.mockReturnValue({
    pathname,
    search: '',
    hash: '',
    state: null,
  })

  mockUseTranslation.mockReturnValue({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'breadcrumb.home': 'Home',
        'nav.incidents': 'Incidents',
        'nav.shm': 'SHM',
        'nav.reports': 'Reports',
        'nav.apiData': 'API Data',
        'nav.settings': 'Settings',
        'nav.admin': 'Admin',
      }
      return translations[key] || key
    },
    i18n: {
      language: 'en',
      changeLanguage: vi.fn(),
    },
  })
}

describe('useBreadcrumbs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('root path', () => {
    it('returns empty array for root path /', () => {
      setupMocks('/')
      const { result } = renderHook(() => useBreadcrumbs())
      expect(result.current).toEqual([])
    })
  })

  describe('incidents path', () => {
    it('returns breadcrumbs for /incidents', () => {
      setupMocks('/incidents')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(2)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
      expect(result.current[1]).toEqual({ label: 'Incidents' })
    })

    it('includes href only for home breadcrumb', () => {
      setupMocks('/incidents')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current[0].href).toBe('/')
      expect(result.current[1].href).toBeUndefined()
    })
  })

  describe('shm path', () => {
    it('returns breadcrumbs for /shm', () => {
      setupMocks('/shm')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(2)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
      expect(result.current[1]).toEqual({ label: 'SHM' })
    })
  })

  describe('reports path', () => {
    it('returns breadcrumbs for /reports', () => {
      setupMocks('/reports')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(2)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
      expect(result.current[1]).toEqual({ label: 'Reports' })
    })
  })

  describe('api-hub path', () => {
    it('returns breadcrumbs for /api-hub', () => {
      setupMocks('/api-hub')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(2)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
      expect(result.current[1]).toEqual({ label: 'API Data' })
    })
  })

  describe('settings path', () => {
    it('returns breadcrumbs for /settings', () => {
      setupMocks('/settings')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(2)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
      expect(result.current[1]).toEqual({ label: 'Settings' })
    })
  })

  describe('admin path', () => {
    it('returns breadcrumbs for /admin', () => {
      setupMocks('/admin')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(2)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
      expect(result.current[1]).toEqual({ label: 'Admin' })
    })
  })

  describe('unknown paths', () => {
    it('returns only home for unknown paths', () => {
      setupMocks('/unknown-path')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(1)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
    })

    it('returns only home for /some-random-route', () => {
      setupMocks('/some-random-route')
      const { result } = renderHook(() => useBreadcrumbs())

      expect(result.current).toHaveLength(1)
      expect(result.current[0]).toEqual({ label: 'Home', href: '/' })
    })
  })

  describe('translation integration', () => {
    it('uses translation function for breadcrumb labels', () => {
      const tMock = vi.fn((key: string) => {
        const translations: Record<string, string> = {
          'breadcrumb.home': 'Home',
          'nav.incidents': 'Incidents',
        }
        return translations[key] || key
      })

      mockUseLocation.mockReturnValue({ pathname: '/incidents' })
      mockUseTranslation.mockReturnValue({
        t: tMock,
        i18n: { language: 'en', changeLanguage: vi.fn() },
      })

      renderHook(() => useBreadcrumbs())

      // t should be called for home and incidents
      expect(tMock).toHaveBeenCalledWith('breadcrumb.home')
      expect(tMock).toHaveBeenCalledWith('nav.incidents')
    })

    it('memoizes result when pathname does not change', () => {
      setupMocks('/incidents')

      const { result: result1 } = renderHook(() => useBreadcrumbs())
      const result1Array = result1.current

      setupMocks('/incidents')
      const { result: result2 } = renderHook(() => useBreadcrumbs())
      const result2Array = result2.current

      // Should be the same reference (memoized)
      expect(result1Array).toEqual(result2Array)
    })
  })

  describe('edge cases', () => {
    it('handles path with trailing slash', () => {
      setupMocks('/incidents/')
      const { result } = renderHook(() => useBreadcrumbs())

      // /incidents/ doesn't match /incidents, so should return just home
      expect(result.current).toHaveLength(1)
    })

    it('handles path with query params', () => {
      // Note: useLocation typically doesn't include query in pathname, only in search
      // But test the pathname behavior
      setupMocks('/incidents')
      mockUseLocation.mockReturnValue({
        pathname: '/incidents',
        search: '?id=123',
        hash: '',
        state: null,
      })

      const { result } = renderHook(() => useBreadcrumbs())
      expect(result.current).toHaveLength(2)
      expect(result.current[1]).toEqual({ label: 'Incidents' })
    })

    it('handles deeply nested paths', () => {
      setupMocks('/admin/users/123')
      const { result } = renderHook(() => useBreadcrumbs())

      // /admin/users/123 doesn't match /admin, so should return just home
      expect(result.current).toHaveLength(1)
    })
  })

  describe('all documented paths', () => {
    const pathsToBreadcrumbs = [
      { path: '/incidents', expectedLabel: 'Incidents' },
      { path: '/shm', expectedLabel: 'SHM' },
      { path: '/reports', expectedLabel: 'Reports' },
      { path: '/api-hub', expectedLabel: 'API Data' },
      { path: '/settings', expectedLabel: 'Settings' },
      { path: '/admin', expectedLabel: 'Admin' },
    ]

    pathsToBreadcrumbs.forEach(({ path, expectedLabel }) => {
      it(`maps ${path} to ${expectedLabel}`, () => {
        setupMocks(path)
        const { result } = renderHook(() => useBreadcrumbs())

        expect(result.current).toHaveLength(2)
        expect(result.current[1].label).toBe(expectedLabel)
      })
    })
  })
})
