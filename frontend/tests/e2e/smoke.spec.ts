import { expect, test } from '@playwright/test'

/**
 * The backend is mocked at the network boundary for this smoke suite — see
 * `playwright.config.ts`'s header comment for why. Every mock below matches
 * the actual response shape documented in `frontend/openapi/karya.openapi.json`
 * (regenerated from the live backend — see `docs/api-types.md`), not a
 * guess at what the API might return.
 */

test.describe('unauthenticated visitor', () => {
  test('is redirected from the app to the login page', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Sign in to Karya' })).toBeVisible()
  })

  test('is redirected away from an admin-only route without ever seeing its content', async ({ page }) => {
    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { name: 'Sign in to Karya' })).toBeVisible()
    await expect(page.getByText('Manage users')).toHaveCount(0)
  })

  test('sees the real backend error for invalid credentials, not a generic failure', async ({ page }) => {
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        headers: { 'X-Request-ID': 'test-request-id' },
        body: JSON.stringify({ detail: 'Invalid credentials' }),
      })
    })

    await page.goto('/login')
    await page.getByLabel('Organization ID').fill('acme')
    await page.getByLabel('Email').fill('riya@acme.com')
    await page.getByLabel('Password').fill('wrong-password-123')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toHaveText('Invalid credentials')
  })

  test('rejects an empty submission with field-level errors before calling the API', async ({ page }) => {
    let loginCalled = false
    await page.route('**/api/v1/auth/login', async (route) => {
      loginCalled = true
      await route.continue()
    })

    await page.goto('/login')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByText('Enter your organization ID')).toBeVisible()
    expect(loginCalled).toBe(false)
  })
})

test.describe('authenticated session', () => {
  test('logs in successfully and reaches the home page with the right greeting', async ({ page }) => {
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'test-access-token',
          refresh_token: 'test-refresh-token',
          token_type: 'bearer',
          expires_in: 900,
        }),
      })
    })
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user-1',
          tenant_id: 'tenant-1',
          employee_code: 'EMP-1',
          name: 'Riya Sharma',
          email: 'riya@acme.com',
          role: 'STAFF',
          status: 'ACTIVE',
        }),
      })
    })
    await page.route('**/api/v1/tenant/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'tenant-1',
          name: 'Acme Co',
          slug: 'acme',
          status: 'ACTIVE',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        }),
      })
    })

    await page.goto('/login')
    await page.getByLabel('Organization ID').fill('acme')
    await page.getByLabel('Email').fill('riya@acme.com')
    await page.getByLabel('Password').fill('correct-password-123')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('heading', { name: /welcome, riya sharma/i })).toBeVisible()
    // A STAFF user's nav must never show admin-only links, checked at the
    // real rendered DOM rather than only at the unit-test level.
    await expect(page.getByRole('navigation', { name: 'Primary' }).first().getByText('Manage users')).toHaveCount(0)
  })
})
