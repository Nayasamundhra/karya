import { expect, test } from '@playwright/test'

/** E2E coverage of tenant-admin employee management (Phase 10 §8, §11-§13). */

async function mockAuth(page: import('@playwright/test').Page) {
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
        id: 'admin-1',
        tenant_id: 'tenant-1',
        employee_code: 'ADM-1',
        name: 'Neha Verma',
        email: 'neha@acme.com',
        role: 'TENANT_ADMIN',
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
}

/**
 * `EmployeeTable` renders a desktop `<table>` and a mobile card list at
 * once, CSS-hidden per breakpoint — so this whole spec (which exercises
 * `<table>`-scoped locators) runs on Desktop Chrome only. The mobile layout
 * is covered by `EmployeeTable`'s own unit tests.
 */
// The empty `{}` is required by Playwright's fixture-destructuring
// convention, even though no fixture is used here.
test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== 'Desktop Chrome', 'exercises the desktop-only <table> layout')
})

function employee(overrides: Record<string, unknown> = {}) {
  return {
    id: 'user-1',
    tenant_id: 'tenant-1',
    employee_code: 'EMP-1',
    name: 'Riya Sharma',
    email: 'riya@acme.com',
    role: 'STAFF',
    status: 'ACTIVE',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Organization ID').fill('acme')
  await page.getByLabel('Email').fill('neha@acme.com')
  await page.getByLabel('Password').fill('correct-password-123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test.describe('tenant admin employee management', () => {
  test('logs in and sees the employee roster', async ({ page }) => {
    await mockAuth(page)
    await page.route('**/api/v1/users?**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [employee()], pagination: { page: 1, page_size: 25, total: 1, total_pages: 1 } }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Manage employees' }).click()

    await expect(page.getByRole('heading', { name: 'Manage employees' })).toBeVisible()
    await expect(page.getByRole('table').getByText('Riya Sharma')).toBeVisible()
    await expect(page.getByRole('table').getByText('Employee', { exact: true })).toBeVisible()
  })

  test('creates a new employee', async ({ page }) => {
    await mockAuth(page)
    let listCallCount = 0
    await page.route('**/api/v1/users?**', async (route) => {
      listCallCount += 1
      const items = listCallCount === 1 ? [employee()] : [employee(), employee({ id: 'user-2', name: 'New Hire', employee_code: 'EMP-9' })]
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items, pagination: { page: 1, page_size: 25, total: items.length, total_pages: 1 } }),
      })
    })
    await page.route('**/api/v1/users', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      const body = route.request().postDataJSON()
      expect(body).toMatchObject({ name: 'New Hire', email: 'new.hire@acme.com', employee_code: 'EMP-9', role: 'STAFF' })
      expect(body).not.toHaveProperty('tenant_id')
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(employee({ id: 'user-2', name: 'New Hire', employee_code: 'EMP-9' })),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Manage employees' }).click()
    await expect(page.getByRole('table').getByText('Riya Sharma')).toBeVisible()

    await page.getByRole('button', { name: /add employee/i }).click()
    await page.getByLabel('Name').fill('New Hire')
    await page.getByLabel('Email').fill('new.hire@acme.com')
    await page.getByLabel('Employee code').fill('EMP-9')
    await page.getByLabel('Password').fill('a-strong-password')
    await page.getByRole('button', { name: /^create employee$/i }).click()

    await expect(page.getByRole('heading', { name: 'Add employee' })).toHaveCount(0)
    await expect(page.getByRole('table').getByText('New Hire')).toBeVisible()
  })

  test('deactivates an employee after confirmation', async ({ page }) => {
    await mockAuth(page)
    let deactivated = false
    await page.route('**/api/v1/users?**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [employee({ status: deactivated ? 'INACTIVE' : 'ACTIVE' })],
          pagination: { page: 1, page_size: 25, total: 1, total_pages: 1 },
        }),
      })
    })
    await page.route('**/api/v1/users/user-1/deactivate', async (route) => {
      deactivated = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(employee({ status: 'INACTIVE' })),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Manage employees' }).click()
    await expect(page.getByRole('table').getByText('Riya Sharma')).toBeVisible()

    await page.getByRole('table').getByRole('button', { name: /actions for riya sharma/i }).click()
    await page.getByRole('menuitem', { name: 'Deactivate' }).click()

    await expect(page.getByRole('heading', { name: 'Deactivate employee?' })).toBeVisible()
    await expect(page.getByText(/riya sharma will no longer be able to sign in/i)).toBeVisible()

    await page.getByRole('button', { name: 'Deactivate' }).click()

    await expect(page.getByRole('heading', { name: 'Deactivate employee?' })).toHaveCount(0)
    await expect(page.getByRole('table').getByText('Inactive')).toBeVisible()
  })
})
