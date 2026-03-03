import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
    test('shows login page for unauthenticated users', async ({ page }) => {
        await page.goto('/login')
        await expect(page.getByRole('heading')).toContainText(/login|sign in|sequoia/i)
        await expect(page.getByLabel(/username|email/i)).toBeVisible()
        await expect(page.getByLabel(/password/i)).toBeVisible()
    })

    test('redirects unauthenticated users to login', async ({ page }) => {
        await page.goto('/')
        await expect(page).toHaveURL(/login/)
    })

    test('login form validates empty fields', async ({ page }) => {
        await page.goto('/login')
        const submitButton = page.getByRole('button', { name: /log in|sign in|submit/i })
        await submitButton.click()
        // Form should not navigate away
        await expect(page).toHaveURL(/login/)
    })
})
