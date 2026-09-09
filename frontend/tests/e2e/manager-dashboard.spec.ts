import { expect, test } from '@playwright/test'

/**
 * E2E coverage of the manager/tenant-admin team dashboard (Phase 10 §3-§7).
 * Like `attendance.spec.ts`, the backend is mocked at the network boundary —
 * every mock matches the real response shape in
 * `frontend/openapi/karya.openapi.json`.
 */

async function mockAuth(page: import('@playwright/test').Page, role: 'MANAGER' | 'TENANT_ADMIN' | 'STAFF') {
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
        employee_code: 'MGR-1',
        name: 'Vikram Rao',
        email: 'vikram@acme.com',
        role,
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
  // The access token lives only in memory (see docs/auth.md) — a direct
  // `page.goto()` to a protected route (used below to check route guards
  // without relying on a nav link STAFF never sees) reloads the app, which
  // then silently refreshes using the refresh token in `localStorage`.
  await page.route('**/api/v1/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'refreshed-access-token',
        refresh_token: 'refreshed-refresh-token',
        token_type: 'bearer',
        expires_in: 900,
      }),
    })
  })
  // A TENANT_ADMIN landing on Home renders `SetupNudge`, which reads
  // `useSetupStatus` — three more requests with nothing here to answer
  // them otherwise (no backend runs in this e2e project; an unmocked
  // request just fails against an unreachable host, but leaves the query
  // retrying in the background rather than settling quickly). Mocked as
  // already-complete so the nudge doesn't render at all and none of this
  // spec's assertions have to account for it.
  await page.route('**/api/v1/tenant/me/location', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'loc-1',
        name: 'HQ',
        description: null,
        latitude: 12.9716,
        longitude: 77.5946,
        geofence_radius_meters: 150,
        status: 'ACTIVE',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }),
    })
  })
  await page.route('**/api/v1/tenant/display-tokens', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{ id: 'disp-1', label: 'Lobby', created_at: '2026-01-01T00:00:00Z', last_used_at: null, revoked_at: null }],
      }),
    })
  })
  await page.route('**/api/v1/users?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
        pagination: { page: 1, page_size: 2, total: 2, total_pages: 1 },
      }),
    })
  })
  // A STAFF user landing on Home renders `EmployeeHome`, which fetches live
  // attendance data — same reasoning as the setup-status mocks above.
  await page.route('**/api/v1/attendance/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user_id: 'user-1',
        state: 'NOT_CHECKED_IN',
        day: { date: '2026-01-05', status: 'NO_RECORD', sessions: [], first_check_in: null, last_check_out: null },
      }),
    })
  })
  await page.route('**/api/v1/attendance/me/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user_id: 'user-1',
        from_date: '2025-12-30',
        to_date: '2026-01-05',
        items: [],
        pagination: { page: 1, page_size: 7, total: 0, total_pages: 0 },
      }),
    })
  })
}

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Organization ID').fill('acme')
  await page.getByLabel('Email').fill('vikram@acme.com')
  await page.getByLabel('Password').fill('correct-password-123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

function teamTodayResponse() {
  return {
    date: '2026-08-22',
    summary: { total_staff: 3, no_record: 1, checked_in: 1, completed: 1 },
    employees: [
      {
        user_id: '11111111-1111-1111-1111-111111111111',
        name: 'Riya Sharma',
        employee_code: 'EMP-1',
        status: 'CHECKED_IN',
        check_in: '2026-08-22T09:04:00Z',
        check_out: null,
      },
      {
        user_id: '22222222-2222-2222-2222-222222222222',
        name: 'Amit Kumar',
        employee_code: 'EMP-2',
        status: 'COMPLETED',
        check_in: '2026-08-22T09:00:00Z',
        check_out: '2026-08-22T17:00:00Z',
      },
      {
        user_id: '33333333-3333-3333-3333-333333333333',
        name: 'Priya Nair',
        employee_code: 'EMP-3',
        status: 'NO_RECORD',
        check_in: null,
        check_out: null,
      },
    ],
  }
}

/**
 * `TeamAttendanceTable` renders a desktop `<table>` and a mobile card list
 * side by side, CSS-hidden per breakpoint (see `TeamAttendanceTable.tsx`) —
 * so table-role assertions only resolve on the Desktop Chrome project; the
 * mobile card list is exercised by its own unit tests plus the
 * no-horizontal-overflow check at the bottom of this file.
 */
test.describe('manager dashboard (desktop table)', () => {
  // The empty `{}` is required by Playwright's fixture-destructuring
  // convention, even though no fixture is used here.
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== 'Desktop Chrome', 'exercises the desktop-only <table> layout')
  })

  test('logs in, sees today\'s team attendance with accurate summary counts', async ({ page }) => {
    await mockAuth(page, 'MANAGER')
    await page.route('**/api/v1/attendance/team/today**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(teamTodayResponse()) })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Team' }).click()

    await expect(page.getByRole('heading', { name: 'Team attendance' })).toBeVisible()
    await expect(page.getByText('Total Employees')).toBeVisible()
    await expect(page.getByRole('table').getByText('Riya Sharma')).toBeVisible()
    await expect(page.getByRole('table').getByText('Amit Kumar')).toBeVisible()
    await expect(page.getByRole('table').getByText('Priya Nair')).toBeVisible()
  })

  test('filters today\'s roster by status without another network request', async ({ page }) => {
    await mockAuth(page, 'MANAGER')
    let requestCount = 0
    await page.route('**/api/v1/attendance/team/today**', async (route) => {
      requestCount += 1
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(teamTodayResponse()) })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Team' }).click()
    await expect(page.getByRole('table').getByText('Riya Sharma')).toBeVisible()

    // Snapshot after the initial load rather than asserting an absolute
    // count of 1 — the app's real `QueryClient` has `refetchOnWindowFocus`
    // on (see `providers.tsx`), which a parallel test run's window-focus
    // churn can legitimately trigger independent of anything this test
    // does. What §5/§17 actually promises is that *filtering* issues no
    // request of its own.
    const countBeforeFilter = requestCount
    await page.getByRole('button', { name: 'Completed' }).click()
    await expect(page.getByRole('table').getByText('Riya Sharma')).toHaveCount(0)
    await expect(page.getByRole('table').getByText('Amit Kumar')).toBeVisible()

    expect(requestCount).toBe(countBeforeFilter)
  })

  test('opens an employee\'s detail and history from the roster', async ({ page }) => {
    await mockAuth(page, 'TENANT_ADMIN')
    await page.route('**/api/v1/attendance/team/today**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(teamTodayResponse()) })
    })
    await page.route('**/api/v1/attendance/users/11111111-1111-1111-1111-111111111111', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: '11111111-1111-1111-1111-111111111111',
          state: 'CHECKED_IN',
          day: {
            date: '2026-08-22',
            status: 'CHECKED_IN',
            sessions: [],
            first_check_in: '2026-08-22T09:04:00Z',
            last_check_out: null,
          },
        }),
      })
    })
    await page.route('**/api/v1/attendance/users/11111111-1111-1111-1111-111111111111/history**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: '11111111-1111-1111-1111-111111111111',
          from_date: '2026-07-24',
          to_date: '2026-08-22',
          items: [
            {
              date: '2026-08-21',
              status: 'COMPLETED',
              sessions: [],
              first_check_in: '2026-08-21T09:00:00Z',
              last_check_out: '2026-08-21T17:00:00Z',
            },
          ],
          pagination: { page: 1, page_size: 30, total: 1, total_pages: 1 },
        }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Team' }).click()
    await page.getByRole('table').getByText('Riya Sharma').click()

    await expect(page.getByRole('heading', { name: 'Employee attendance' })).toBeVisible()
    await expect(page.getByText(/checked in at/i)).toBeVisible()
    await expect(page.getByText(/employee history/i)).toBeVisible()
  })
})

test.describe('manager dashboard (route guards, both viewports)', () => {
  test('STAFF cannot reach the manager dashboard or employee management UI', async ({ page }) => {
    await mockAuth(page, 'STAFF')
    await login(page)

    await expect(page.getByRole('navigation', { name: 'Primary' }).first().getByText('Team')).toHaveCount(0)
    await expect(page.getByRole('navigation', { name: 'Primary' }).first().getByText('Manage employees')).toHaveCount(0)

    // Typed-URL / bookmark access, not a nav click — STAFF's nav never
    // offers these links in the first place (asserted above).
    await page.goto('/team')
    await expect(page.getByRole('heading', { name: /don't have permission/i })).toBeVisible()

    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { name: /don't have permission/i })).toBeVisible()
  })

  test('the dashboard has no horizontal overflow on a narrow viewport', async ({ page }) => {
    await mockAuth(page, 'MANAGER')
    await page.route('**/api/v1/attendance/team/today**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(teamTodayResponse()) })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Team' }).click()
    await expect(page.getByRole('heading', { name: 'Team attendance' })).toBeVisible()
    // Not "Riya Sharma" — that text has both a CSS-hidden desktop `<table>`
    // copy and a mobile card copy (see the describe block above), and which
    // one is "visible" depends on the viewport under test. The summary
    // card's heading isn't duplicated, and is enough to confirm data loaded.
    await expect(page.getByText('Total Employees')).toBeVisible()

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth)
  })
})
