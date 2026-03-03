import { test, expect } from '@playwright/test'

async function mockAuth(page: any) {
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
    await page.route('**/api/**', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ results: [], hasMore: false, limit: 0 }),
        })
    })
    await page.route('**/ws/**', route => route.abort())
}

test.describe('Dark Mode', () => {
    test.beforeEach(async ({ page }) => {
        await mockAuth(page)
    })

    test('dark mode toggle exists in header', async ({ page }) => {
        await page.goto('/')
        await page.waitForTimeout(2000)
        const toggle = page.getByRole('button', { name: /dark|light|theme/i })
        await expect(toggle).toBeVisible()
    })

    test('clicking toggle adds dark class to html element', async ({ page }) => {
        await page.goto('/')
        await page.waitForTimeout(2000)
        const toggle = page.getByRole('button', { name: /dark|light|theme/i })

        // Initially should be light (no dark class)
        const htmlClass = await page.locator('html').getAttribute('class')
        expect(htmlClass).not.toContain('dark')

        // Click toggle
        await toggle.click()

        // Should now have dark class
        const updatedClass = await page.locator('html').getAttribute('class')
        expect(updatedClass).toContain('dark')
    })

    test('dark mode persists across page navigation', async ({ page }) => {
        await page.goto('/')
        await page.waitForTimeout(2000)
        const toggle = page.getByRole('button', { name: /dark|light|theme/i })
        await toggle.click()

        // Navigate to incidents
        await page.goto('/incidents')
        await page.waitForTimeout(2000)

        // Dark class should persist
        const htmlClass = await page.locator('html').getAttribute('class')
        expect(htmlClass).toContain('dark')
    })

    test('dark mode preference saved to localStorage', async ({ page }) => {
        await page.goto('/')
        await page.waitForTimeout(2000)
        const toggle = page.getByRole('button', { name: /dark|light|theme/i })
        await toggle.click()

        const theme = await page.evaluate(() => localStorage.getItem('sequoia_theme'))
        expect(theme).toBe('dark')
    })
})
