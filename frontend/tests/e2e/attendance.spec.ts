import { expect, test } from '@playwright/test'

import { stubCameraUnavailable, stubCameraWithQrPayload } from './helpers/fakeCamera'

/**
 * End-to-end coverage of the employee attendance experience (§20). Like
 * `smoke.spec.ts`, the backend is mocked at the network boundary — every
 * mock below matches the real response shape in
 * `frontend/openapi/karya.openapi.json`. GPS is Playwright's own
 * geolocation emulation (a real, supported browser API — no fake object);
 * the camera is faked at the hardware boundary only (see `helpers/fakeCamera.ts`),
 * so the app's real QR-decode and attendance logic runs unmodified in both.
 */

const CHALLENGE_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
const QR_PAYLOAD = { challenge_id: CHALLENGE_ID, nonce: 'office-display-nonce' }

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
}

function todayResponse(status: 'NO_RECORD' | 'CHECKED_IN' | 'COMPLETED', checkIn?: string, checkOut?: string) {
  return {
    user_id: 'user-1',
    state: status === 'CHECKED_IN' ? 'CHECKED_IN' : 'NOT_CHECKED_IN',
    day: {
      date: '2026-08-22',
      status,
      sessions: [],
      first_check_in: checkIn ?? null,
      last_check_out: checkOut ?? null,
    },
  }
}

function emptyHistory() {
  return {
    user_id: 'user-1',
    from_date: '2026-08-09',
    to_date: '2026-08-22',
    items: [],
    pagination: { page: 1, page_size: 14, total: 0, total_pages: 0 },
  }
}

async function mockToday(page: import('@playwright/test').Page, response: unknown) {
  await page.route('**/api/v1/attendance/me', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) })
  })
}

async function mockHistory(page: import('@playwright/test').Page, response: unknown = emptyHistory()) {
  await page.route('**/api/v1/attendance/me/history**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) })
  })
}

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Organization ID').fill('acme')
  await page.getByLabel('Email').fill('riya@acme.com')
  await page.getByLabel('Password').fill('correct-password-123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 12.9716, longitude: 77.5946, accuracy: 10 })
  await mockAuth(page)
})

test.describe('employee attendance home', () => {
  test('logs in and lands on Attendance showing the NO_RECORD state', async ({ page }) => {
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)
    await login(page)

    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await expect(page.getByText('Not checked in').first()).toBeVisible()
    await expect(page.getByRole('link', { name: /^check in$/i })).toBeVisible()

    // §23/§28: product copy says "Employee", never the bare word "Staff".
    await expect(page.getByText(/\bStaff\b/)).toHaveCount(0)
  })

  test('shows the CHECKED_IN state with a Check out action', async ({ page }) => {
    await mockToday(page, todayResponse('CHECKED_IN', '2026-08-22T09:04:00Z'))
    await mockHistory(page)
    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()

    await expect(page.getByText("You're checked in")).toBeVisible()
    await expect(page.getByRole('link', { name: /^check out$/i })).toBeVisible()
  })
})

test.describe('check-in flow', () => {
  test('a full check-in succeeds against a real (faked-camera) QR scan and real GPS emulation', async ({ page }) => {
    await stubCameraWithQrPayload(page, QR_PAYLOAD)
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)

    let checkInCalled = false
    await page.route('**/api/v1/attendance/check-in', async (route) => {
      checkInCalled = true
      const body = route.request().postDataJSON()
      expect(body).toMatchObject({ challenge_id: CHALLENGE_ID, nonce: 'office-display-nonce' })
      expect(body).not.toHaveProperty('tenant_id')
      expect(body).not.toHaveProperty('user_id')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          event_type: 'CHECK_IN',
          status: 'CHECKED_IN',
          attendance_event_id: 'evt-1',
          event_timestamp: '2026-08-22T09:04:00Z',
          presence: null,
          reason: null,
        }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check in/i }).first().click()
    await page.getByRole('button', { name: /start check-in/i }).click()

    await expect(page.getByText('Check-in successful')).toBeVisible({ timeout: 15_000 })
    expect(checkInCalled).toBe(true)
    await expect(page.getByText("You're checked in.")).toBeVisible()
  })

  test('an expired QR is reported clearly and offers a re-scan', async ({ page }) => {
    await stubCameraWithQrPayload(page, QR_PAYLOAD)
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)
    await page.route('**/api/v1/attendance/check-in', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          event_type: 'CHECK_IN',
          status: 'NOT_CHECKED_IN',
          attendance_event_id: null,
          event_timestamp: null,
          presence: null,
          reason: 'QR_EXPIRED',
        }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check in/i }).first().click()
    await page.getByRole('button', { name: /start check-in/i }).click()

    await expect(page.getByText(/this qr code has expired/i)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: /scan again/i })).toBeVisible()
  })

  test('a low-accuracy GPS rejection shows the accuracy-specific message', async ({ page }) => {
    await stubCameraWithQrPayload(page, QR_PAYLOAD)
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)
    await page.route('**/api/v1/attendance/check-in', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          event_type: 'CHECK_IN',
          status: 'NOT_CHECKED_IN',
          attendance_event_id: null,
          event_timestamp: null,
          presence: null,
          reason: 'GPS_ACCURACY_TOO_LOW',
        }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check in/i }).first().click()
    await page.getByRole('button', { name: /start check-in/i }).click()

    await expect(page.getByText(/clearer gps signal/i)).toBeVisible({ timeout: 15_000 })
  })

  test('a geofence rejection is shown without the client ever claiming to know the office location', async ({
    page,
  }) => {
    await stubCameraWithQrPayload(page, QR_PAYLOAD)
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)
    await page.route('**/api/v1/attendance/check-in', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          event_type: 'CHECK_IN',
          status: 'NOT_CHECKED_IN',
          attendance_event_id: null,
          event_timestamp: null,
          presence: null,
          reason: 'OUTSIDE_GEOFENCE',
        }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check in/i }).first().click()
    await page.getByRole('button', { name: /start check-in/i }).click()

    await expect(page.getByText(/outside the office area/i)).toBeVisible({ timeout: 15_000 })
    // Never a "Scan again" here — the QR is still valid; only GPS failed.
    await expect(page.getByRole('button', { name: /scan again/i })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /try again/i })).toBeVisible()
  })

  test('a dropped connection never claims success, and offers an explicit retry', async ({ page }) => {
    await stubCameraWithQrPayload(page, QR_PAYLOAD)
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)
    await page.route('**/api/v1/attendance/check-in', async (route) => {
      await route.abort('failed')
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check in/i }).first().click()
    await page.getByRole('button', { name: /start check-in/i }).click()

    await expect(page.getByText("Couldn't connect to Karya")).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Your attendance was not confirmed.')).toBeVisible()
    await expect(page.getByText('Check-in successful')).toHaveCount(0)
  })

  test('a camera-less device gets a clear message instead of a stuck spinner', async ({ page }) => {
    await stubCameraUnavailable(page)
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check in/i }).first().click()
    await page.getByRole('button', { name: /start check-in/i }).click()

    await expect(page.getByText(/no camera was found/i)).toBeVisible({ timeout: 15_000 })
  })
})

test.describe('check-out flow', () => {
  test('a full check-out succeeds and reports the check-out-specific copy', async ({ page }) => {
    await stubCameraWithQrPayload(page, QR_PAYLOAD)
    await mockToday(page, todayResponse('CHECKED_IN', '2026-08-22T09:04:00Z'))
    await mockHistory(page)
    await page.route('**/api/v1/attendance/check-out', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          event_type: 'CHECK_OUT',
          status: 'NOT_CHECKED_IN',
          attendance_event_id: 'evt-2',
          event_timestamp: '2026-08-22T17:30:00Z',
          presence: null,
          reason: null,
        }),
      })
    })

    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await page.getByRole('link', { name: /check out/i }).first().click()
    await page.getByRole('button', { name: /start check-out/i }).click()

    await expect(page.getByText('Check-out successful')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("You're checked out.")).toBeVisible()
  })
})

test.describe('mobile viewport', () => {
  test('the attendance home has no horizontal overflow', async ({ page }) => {
    await mockToday(page, todayResponse('NO_RECORD'))
    await mockHistory(page)
    await login(page)
    await page.getByRole('navigation', { name: 'Primary' }).first().getByRole('link', { name: 'Attendance' }).click()
    await expect(page.getByText('Not checked in').first()).toBeVisible()

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth)
  })
})
