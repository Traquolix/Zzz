import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePermissions } from './usePermissions'
import type { AuthContextType } from '@/context/AuthContext'

// Mock the useAuth hook
vi.mock('./useAuth', () => ({
  useAuth: vi.fn(),
}))

// Import after mocking
import { useAuth } from './useAuth'

const mockUseAuth = useAuth as ReturnType<typeof vi.fn>

// Helper to render hook with custom auth context
function renderPermissionsHook(authContext: AuthContextType) {
  mockUseAuth.mockReturnValue(authContext)
  return renderHook(() => usePermissions())
}

describe('usePermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('hasWidget', () => {
    it('returns true for allowed widget', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents', 'shm'],
        allowedLayers: ['layer1'],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.hasWidget('incidents')).toBe(true)
      expect(result.current.hasWidget('shm')).toBe(true)
    })

    it('returns false for disallowed widget', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents'],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.hasWidget('admin')).toBe(false)
      expect(result.current.hasWidget('shm')).toBe(false)
    })

    it('returns false when allowedWidgets is empty', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.hasWidget('incidents')).toBe(false)
      expect(result.current.hasWidget('admin')).toBe(false)
    })
  })

  describe('hasLayer', () => {
    it('returns true for allowed layer', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: ['fiber_layer', 'segment_layer'],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.hasLayer('fiber_layer')).toBe(true)
      expect(result.current.hasLayer('segment_layer')).toBe(true)
    })

    it('returns false for disallowed layer', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: ['fiber_layer'],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.hasLayer('admin_layer')).toBe(false)
      expect(result.current.hasLayer('segment_layer')).toBe(false)
    })

    it('returns false when allowedLayers is empty', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.hasLayer('fiber_layer')).toBe(false)
    })
  })

  describe('canAccessPage', () => {
    it('allows access to root path', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.canAccessPage('/')).toBe(true)
    })

    it('allows access to pages without requiredWidget', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      // /api-hub and /settings have no requiredWidget
      expect(result.current.canAccessPage('/api-hub')).toBe(true)
      expect(result.current.canAccessPage('/settings')).toBe(true)
    })

    it('denies access to pages with requiredWidget when not allowed', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      // /incidents requires 'incidents' widget
      // /admin requires 'admin' widget
      expect(result.current.canAccessPage('/incidents')).toBe(false)
      expect(result.current.canAccessPage('/admin')).toBe(false)
    })

    it('allows access to pages with requiredWidget when allowed', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents', 'admin'],
        allowedLayers: [],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.canAccessPage('/incidents')).toBe(true)
      expect(result.current.canAccessPage('/admin')).toBe(true)
    })

    it('is case-insensitive', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents'],
        allowedLayers: [],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.canAccessPage('/INCIDENTS')).toBe(true)
      expect(result.current.canAccessPage('/Incidents')).toBe(true)
      expect(result.current.canAccessPage('/incidents')).toBe(true)
    })

    it('allows unknown routes (lets router handle 404)', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.canAccessPage('/unknown-route')).toBe(true)
      expect(result.current.canAccessPage('/nonexistent')).toBe(true)
    })

    it('checks alternate routes', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['shm'],
        allowedLayers: [],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      // /shm is an alternate of /incidents with requiredWidget 'shm'
      expect(result.current.canAccessPage('/shm')).toBe(true)
    })

    it('denies alternate routes when not allowed', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      // /shm requires 'shm' widget
      expect(result.current.canAccessPage('/shm')).toBe(false)
    })
  })

  describe('visibleNavItems', () => {
    it('shows all items when user has all widgets', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents', 'shm', 'admin'],
        allowedLayers: [],
        role: 'superuser',
        isSuperuser: true,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      // Home has no requiredWidget
      // incidents requires 'incidents'
      // reports requires 'incidents'
      // api-hub has no requiredWidget
      // settings has no requiredWidget
      // admin requires 'admin'
      expect(result.current.visibleNavItems.length).toBeGreaterThanOrEqual(4)
    })

    it('filters items based on required widgets', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents'],
        allowedLayers: [],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      const paths = result.current.visibleNavItems.map(item => item.path)

      // Should include items without requiredWidget and with 'incidents' widget
      expect(paths).toContain('/')
      expect(paths).toContain('/incidents')
      expect(paths).toContain('/reports')
      expect(paths).toContain('/api-hub')
      expect(paths).toContain('/settings')
      // Should not include admin
      expect(paths).not.toContain('/admin')
    })

    it('shows only no-widget items for viewer', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      const paths = result.current.visibleNavItems.map(item => item.path)

      // Should only include items without requiredWidget
      expect(paths).toContain('/')
      expect(paths).toContain('/api-hub')
      expect(paths).toContain('/settings')
      // Should not include widget-restricted items
      expect(paths).not.toContain('/incidents')
      expect(paths).not.toContain('/reports')
      expect(paths).not.toContain('/admin')
    })

    it('includes home page for all users', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: [],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      const homePath = result.current.visibleNavItems.find(item => item.path === '/')
      expect(homePath).toBeDefined()
    })
  })

  describe('allowedWidgets and allowedLayers', () => {
    it('exposes allowedWidgets from context', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: ['incidents', 'shm'],
        allowedLayers: ['layer1', 'layer2'],
        role: 'org_admin',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.allowedWidgets).toEqual(['incidents', 'shm'])
    })

    it('exposes allowedLayers from context', () => {
      const authContext: AuthContextType = {
        isAuthenticated: true,
        isLoading: false,
        username: 'user1',
        organizationId: 'org1',
        organizationName: 'Org 1',
        allowedWidgets: [],
        allowedLayers: ['fiber_layer', 'segment_layer'],
        role: 'viewer',
        isSuperuser: false,
        login: vi.fn(),
        logout: vi.fn(),
      }

      const { result } = renderPermissionsHook(authContext)
      expect(result.current.allowedLayers).toEqual(['fiber_layer', 'segment_layer'])
    })
  })
})
