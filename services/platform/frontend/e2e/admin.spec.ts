import { test, expect } from '@playwright/test'

async function mockSuperuserAuth(page: any) {
    await page.route('**/api/auth/refresh', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                token: 'mock-token',
                username: 'superadmin',
                organizationId: 'org-1',
                organizationName: 'Test Org',
                allowedWidgets: ['map', 'traffic_monitor', 'incidents', 'shm', 'admin'],
                allowedLayers: ['cables', 'fibers', 'vehicles', 'heatmap', 'landmarks', 'sections', 'detections', 'incidents', 'infrastructure'],
                role: 'admin',
                isSuperuser: true,
            }),
        })
    })
    await page.route('**/api/admin/organizations', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                results: [
                    { id: 'org-1', name: 'Acme Corp', slug: 'acme', isActive: true, allowedWidgets: [], allowedLayers: [], fiberAssignments: [] },
                    { id: 'org-2', name: 'Beta Inc', slug: 'beta', isActive: true, allowedWidgets: [], allowedLayers: [], fiberAssignments: [] },
                ],
                hasMore: false,
                limit: 2,
            }),
        })
    })
    await page.route('**/api/admin/users', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                results: [
                    { id: 'u-1', username: 'alice', email: 'alice@test.com', role: 'admin', organizationName: 'Acme Corp', isActive: true, allowedWidgets: [], allowedLayers: [] },
                ],
                hasMore: false,
                limit: 1,
            }),
        })
    })
    await page.route('**/api/admin/infrastructure', route => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [], hasMore: false, limit: 0 }) })
    })
    await page.route('**/api/admin/alert-rules', route => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [], hasMore: false, limit: 0 }) })
    })
    await page.route('**/api/admin/alert-logs', route => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [], hasMore: false, limit: 0 }) })
    })
    await page.route('**/api/**', route => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [], hasMore: false, limit: 0 }) })
    })
    await page.route('**/ws/**', route => route.abort())
}

test.describe('Admin Panel', () => {
    test.beforeEach(async ({ page }) => {
        await mockSuperuserAuth(page)
    })

    test('superuser sees organizations tab', async ({ page }) => {
        await page.goto('/admin')
        await page.waitForTimeout(3000)
        const tab = page.getByRole('tab', { name: /organizations/i })
        await expect(tab).toBeVisible()
    })

    test('admin search filters organizations', async ({ page }) => {
        await page.goto('/admin')
        await page.waitForTimeout(3000)

        const searchInput = page.getByPlaceholderText(/search/i)
        await expect(searchInput).toBeVisible()

        await searchInput.fill('Acme')
        await page.waitForTimeout(500)

        // Should show Acme Corp, hide Beta Inc
        await expect(page.getByText('Acme Corp')).toBeVisible()
        await expect(page.getByText('Beta Inc')).not.toBeVisible()
    })

    test('tab switching clears search', async ({ page }) => {
        await page.goto('/admin')
        await page.waitForTimeout(3000)

        const searchInput = page.getByPlaceholderText(/search/i)
        await searchInput.fill('test')

        // Switch to users tab
        const usersTab = page.getByRole('tab', { name: /users/i })
        await usersTab.click()
        await page.waitForTimeout(1000)

        // Search should be cleared
        const newSearchInput = page.getByPlaceholderText(/search/i)
        await expect(newSearchInput).toHaveValue('')
    })
})
