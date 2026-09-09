import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/app/router'
import type { UserResponse } from '@/lib/api/types'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/tenant', async (importOriginal) => {
  // `vi.mock` factories are hoisted above every top-level import, so
  // `ApiError` is pulled in with its own dynamic `import()` here rather
  // than the file's static import (which would be in the temporal dead
  // zone at the point this factory actually runs).
  const { ApiError } = await import('@/lib/api/errors')
  return {
    ...(await importOriginal<typeof import('@/lib/api/endpoints/tenant')>()),
    getOwnTenant: vi.fn().mockResolvedValue({
      id: 'tenant-1',
      name: 'Acme Co',
      slug: 'acme',
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }),
    // `OrganizationPage`'s `SetupProgressStrip` (via `useSetupStatus`) reads
    // this too — a 404/not_found is the real "no location configured yet"
    // shape `useLocation` expects, not an error.
    getOwnLocation: vi
      .fn()
      .mockRejectedValue(new ApiError({ kind: 'not_found', message: 'Not found', status: 404 })),
  }
})

// `SetupProgressStrip` also reads these two, same reasoning as above.
vi.mock('@/lib/api/endpoints/display', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/display')>()),
  listDisplayTokens: vi.fn().mockResolvedValue({ items: [] }),
}))
vi.mock('@/lib/api/endpoints/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/users')>()),
  listUsers: vi.fn().mockResolvedValue({
    items: [],
    pagination: { page: 1, page_size: 2, total: 1, total_pages: 1 },
  }),
}))

// The employee home (`EmployeeHome`) fetches live attendance data — mocked
// here so STAFF-at-`/` renders deterministically rather than hitting a real
// network call from jsdom.
vi.mock('@/lib/api/endpoints/attendance', () => ({
  getMyAttendance: vi.fn().mockResolvedValue({
    user_id: 'user-1',
    state: 'NOT_CHECKED_IN',
    day: { date: '2026-01-05', status: 'NO_RECORD', sessions: [], first_check_in: null, last_check_out: null },
  }),
  getMyHistory: vi.fn().mockResolvedValue({
    user_id: 'user-1',
    from_date: '2025-12-30',
    to_date: '2026-01-05',
    items: [],
    pagination: { page: 1, page_size: 7, total: 0, total_pages: 0 },
  }),
}))

function fakeUser(role: UserResponse['role']): UserResponse {
  return {
    id: 'user-1',
    tenant_id: 'tenant-1',
    employee_code: 'EMP-1',
    name: 'Riya Sharma',
    email: 'riya@acme.com',
    role,
    status: 'ACTIVE',
  }
}

function renderAt(initialPath: string) {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] })
  return render(
    <TestQueryProvider>
      <RouterProvider router={router} />
    </TestQueryProvider>,
  )
}

function signInAs(role: UserResponse['role']) {
  useAuthStore.setState({
    status: 'authenticated',
    user: fakeUser(role),
    accessToken: 'test-access-token',
    accessTokenExpiresAt: Date.now() + 15 * 60 * 1000,
  })
}

describe('routing and role-based access', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    useAuthStore.getState().clearSession()
  })

  it('redirects an unauthenticated visitor from a protected route to /login', async () => {
    useAuthStore.setState({ status: 'unauthenticated', user: null, accessToken: null, accessTokenExpiresAt: null })
    renderAt('/')
    expect(await screen.findByRole('heading', { name: /sign in to karya/i })).toBeInTheDocument()
  })

  it('lets STAFF reach the home page, and shows only STAFF-appropriate navigation', async () => {
    signInAs('STAFF')
    renderAt('/')

    expect(
      await screen.findByRole('heading', { name: /good (morning|afternoon|evening), riya/i }),
    ).toBeInTheDocument()
    // The greeting renders before `EmployeeHome`'s attendance/history queries
    // resolve — waiting for the check-in hero too drains those mocked
    // promises inside this test's own act() boundary, rather than leaving
    // them pending to resolve during whichever test runs next.
    expect(await screen.findByText(/checked in at|haven.t checked in/i)).toBeInTheDocument()
    await screen.findByText('This week') // drains WeekStats'/WeekHoursCard's separate history query too

    const nav = screen.getAllByRole('navigation', { name: 'Primary' })[0]
    expect(nav).toBeTruthy()
    expect(within(nav).getByText('Home')).toBeInTheDocument()
    expect(within(nav).getByText('Attendance')).toBeInTheDocument()
    expect(within(nav).queryByText('Team')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Manage employees')).not.toBeInTheDocument()
  })

  it('blocks STAFF from an admin-only route with a 403 page, not the admin content', async () => {
    signInAs('STAFF')
    renderAt('/admin/users')
    expect(await screen.findByRole('heading', { name: /don't have permission/i })).toBeInTheDocument()
    expect(screen.queryByText(/manage employees/i)).not.toBeInTheDocument()
  })

  it('lets TENANT_ADMIN reach the admin-only route', async () => {
    signInAs('TENANT_ADMIN')
    renderAt('/admin/users')
    expect(await screen.findByRole('heading', { name: /^manage employees$/i })).toBeInTheDocument()
  })

  it('lets MANAGER reach the team route', async () => {
    signInAs('MANAGER')
    renderAt('/team')
    expect(await screen.findByRole('heading', { name: /team attendance/i })).toBeInTheDocument()
  })

  it('blocks MANAGER from a TENANT_ADMIN-only route', async () => {
    signInAs('MANAGER')
    renderAt('/admin/users')
    expect(await screen.findByRole('heading', { name: /don't have permission/i })).toBeInTheDocument()
  })

  it('lets MANAGER reach an employee detail route', async () => {
    signInAs('MANAGER')
    renderAt('/team/11111111-1111-1111-1111-111111111111')
    expect(await screen.findByRole('heading', { name: /^employee attendance$/i })).toBeInTheDocument()
  })

  it('blocks STAFF from an employee detail route', async () => {
    signInAs('STAFF')
    renderAt('/team/11111111-1111-1111-1111-111111111111')
    expect(await screen.findByRole('heading', { name: /don't have permission/i })).toBeInTheDocument()
  })

  it('renders both the desktop sidebar and the mobile bottom nav in the DOM (CSS, not JS, decides which is visible)', async () => {
    signInAs('STAFF')
    renderAt('/')
    await screen.findByRole('heading', { name: /good (morning|afternoon|evening), riya/i })
    // Drain EmployeeHome's mocked attendance/history queries within this
    // test's own act() boundary — see the earlier STAFF-at-`/` test.
    await screen.findByText(/checked in at|haven.t checked in/i)
    await screen.findByText('This week')
    const navs = screen.getAllByRole('navigation', { name: 'Primary' })
    expect(navs).toHaveLength(2)
  })

  it('renders an unknown path as the 404 page', async () => {
    signInAs('STAFF')
    renderAt('/this-page-does-not-exist')
    expect(await screen.findByText('404')).toBeInTheDocument()
  })

  it('lets a signed-out visitor reach the onboarding page', async () => {
    useAuthStore.setState({ status: 'unauthenticated', user: null, accessToken: null, accessTokenExpiresAt: null })
    renderAt('/onboarding')
    expect(await screen.findByRole('heading', { name: /create your organization/i })).toBeInTheDocument()
  })

  it('redirects an already-signed-in visitor away from onboarding, like /login', async () => {
    signInAs('TENANT_ADMIN')
    renderAt('/onboarding')
    expect(await screen.findByRole('heading', { name: /welcome, riya sharma/i })).toBeInTheDocument()
    // Drains HomePage's SetupNudge (`useSetupStatus`) queries within this
    // test's own act() boundary (see the STAFF-at-`/` tests above).
    await screen.findByText(/finish setting up your organization/i)
  })

  it('lets TENANT_ADMIN reach the organization admin route', async () => {
    signInAs('TENANT_ADMIN')
    renderAt('/admin/organization')
    expect(await screen.findByRole('heading', { name: /^organization$/i, level: 1 })).toBeInTheDocument()
    // Drains SetupProgressStrip's location/display/employee queries within
    // this test's own act() boundary (see the STAFF-at-`/` tests above).
    await screen.findByText(/^setup ·/i)
  })

  it('lets MANAGER reach the organization route, narrowed to just Displays', async () => {
    // MANAGER is one of the backend's QR_ISSUER_ROLES — it may manage
    // display tokens exactly like TENANT_ADMIN, so it reaches this route
    // too, just without the Details/Location tabs (`OrganizationPage`).
    signInAs('MANAGER')
    renderAt('/admin/organization')
    expect(await screen.findByRole('heading', { name: /^displays$/i, level: 1 })).toBeInTheDocument()
    // Drains DisplayTokensCard's own location/display-list queries within
    // this test's own act() boundary (see the STAFF-at-`/` tests above).
    await screen.findByText(/set up an attendance location first/i)
  })

  it('renders the office-display kiosk with no login and no app shell', async () => {
    useAuthStore.setState({ status: 'unauthenticated', user: null, accessToken: null, accessTokenExpiresAt: null })
    renderAt('/display')
    expect(await screen.findByRole('heading', { name: /set up this display/i })).toBeInTheDocument()
    // Standalone: none of the authenticated shell's navigation renders here.
    expect(screen.queryAllByRole('navigation', { name: 'Primary' })).toHaveLength(0)
  })
})
