import React from 'react'
import { describe, test, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { APIHub } from './APIHub'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const translations: Record<string, string> = {
        'apiHub.title': 'API & Data Hub',
        'apiHub.description': 'Access your data through the REST API.',
        'apiHub.authentication': 'Authentication',
        'apiHub.authDescription': 'Bearer token or API Key.',
        'apiHub.baseUrl': 'Base URL',
        'apiHub.endpoints': 'Available Endpoints',
        'apiHub.apiKeyAuth': 'API Key Authentication',
        'apiHub.apiKeyDescription': 'Use X-API-Key header for programmatic access.',
        'apiHub.webhooks': 'Webhooks',
        'apiHub.webhookDescription': 'Verify payloads with X-Sequoia-Signature.',
        'apiHub.rateLimits': 'Rate Limits',
        'apiHub.rateLimitsDescription': 'API requests are rate-limited.',
        'apiHub.requestsPerMinute': `${opts?.count ?? 60} requests/minute`,
        'apiHub.docsLink': 'Full API Documentation',
        'apiHub.docsDescription': 'See the complete API reference.',
        'apiHub.endpointList.incidents': 'Incident history and active alerts',
        'apiHub.endpointList.fibers': 'Fiber line metadata and geometry',
        'apiHub.endpointList.reports': 'Generated traffic reports',
        'apiHub.endpointList.exportIncidents': 'Export incident data (CSV/JSON)',
        'apiHub.endpointList.exportSpeeds': 'Export speed data (CSV/JSON)',
        'apiHub.endpointList.exportCounts': 'Export count data (CSV/JSON)',
        'apiHub.endpointList.stats': 'Traffic statistics',
        'apiHub.endpointList.infrastructure': 'SHM infrastructure data',
      }
      return translations[key] ?? key
    },
  }),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ organizationName: 'Test Org' }),
}))

vi.mock('@/hooks/useCopyToClipboard', () => ({
  useCopyToClipboard: () => ({ copy: vi.fn(), copied: false, isCopied: () => false }),
}))

vi.mock('@/constants/api', () => ({
  API_URL: 'http://localhost:8001',
}))

vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

describe('APIHub', () => {
  test('does not list non-existent endpoints', () => {
    render(<APIHub />)
    expect(screen.queryByText('/api/detections')).not.toBeInTheDocument()
    expect(screen.queryByText('/api/speed-stats')).not.toBeInTheDocument()
  })

  test('lists actual API endpoints', () => {
    render(<APIHub />)
    expect(screen.getByText('/api/incidents')).toBeInTheDocument()
    expect(screen.getByText('/api/fibers')).toBeInTheDocument()
    expect(screen.getByText('/api/export/incidents')).toBeInTheDocument()
  })

  test('documents API key authentication', () => {
    render(<APIHub />)
    expect(screen.getAllByText(/API Key/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/X-API-Key/i).length).toBeGreaterThan(0)
  })

  test('documents webhook payloads', () => {
    render(<APIHub />)
    expect(screen.getAllByText(/Webhook/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/X-Sequoia-Signature/i).length).toBeGreaterThan(0)
  })
})
