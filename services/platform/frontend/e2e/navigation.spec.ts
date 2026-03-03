import { test, expect } from '@playwright/test'

// Helper to mock an authenticated session
async function mockAuth(page: any) {
    // Intercept the refresh token endpoint to simulate authenticated session
    await page.route('**/api/auth/refresh', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                token: 'mock-access-token',
                username: 'testuser',
                organizationId: 'org-1',
                organizationName: 'Test Org',
                allowedWidgets: ['map', 'traffic_monitor', 'incidents', 'shm', 'admin'],
                allowedLayers: ['cables', 'fibers', 'vehicles', 'heatmap', 'landmarks', 'sections', 'detections', 'incidents', 'infrastructure'],
                role: 'admin',
                isSuperuser: true,
            }),
        })
    })

    // Mock all API endpoints that pages call on load
    await page.route('**/api/fibers', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ results: [], hasMore: false, limit: 0 }),
        })
    })
    await page.route('**/api/incidents', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ results: [], hasMore: false, limit: 0 }),
        })
    })
    await page.route('**/api/preferences', route => {
        if (route.request().method() === 'GET') {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({}),
            })
        } else {
            route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
        }
    })
    await page.route('**/api/admin/**', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ results: [], hasMore: false, limit: 0 }),
        })
    })
    await page.route('**/api/reports**', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ results: [], hasMore: false, limit: 0 }),
        })
    })
    await page.route('**/api/shm/**', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ results: [], hasMore: false, limit: 0 }),
        })
    })
    await page.route('**/ws/**', route => {
        route.abort()
    })
}

test.describe('Navigation', () => {
    test.beforeEach(async ({ page }) => {
        await mockAuth(page)
    })

    test('authenticated user sees dashboard', async ({ page }) => {
        await page.goto('/')
        await expect(page.locator('[class*="dashboard"], h1, [data-testid]')).toBeVisible({ timeout: 10000 })
    })

    test('sidebar navigation links are visible', async ({ page }) => {
        await page.goto('/')
        // Wait for app to render
        await page.waitForTimeout(2000)
        // Check nav items exist (desktop nav)
        const nav = page.locator('nav[aria-label="Main navigation"]')
        await expect(nav).toBeVisible()
    })

    test('can navigate to incidents page', async ({ page }) => {
        await page.goto('/incidents')
        await page.waitForTimeout(2000)
        await expect(page.getByText(/incidents/i).first()).toBeVisible()
    })

    test('can navigate to reports page', async ({ page }) => {
        await page.goto('/reports')
        await page.waitForTimeout(2000)
        await expect(page.getByText(/reports/i).first()).toBeVisible()
    })

    test('can navigate to admin page', async ({ page }) => {
        await page.goto('/admin')
        await page.waitForTimeout(2000)
        await expect(page.getByText(/admin/i).first()).toBeVisible()
    })
})
