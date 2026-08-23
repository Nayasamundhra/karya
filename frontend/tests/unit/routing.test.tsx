import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { routes } from '@/app/router'
import type { UserResponse } from '@/lib/api/types'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/tenant', () => ({
  getOwnTenant: vi.fn().mockResolvedValue({
    id: 'tenant-1',
    name: 'Acme Co',
    slug: 'acme',
    status: 'ACTIVE',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
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

    expect(await screen.findByRole('heading', { name: /welcome, riya sharma/i })).toBeInTheDocument()

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
    await screen.findByRole('heading', { name: /welcome/i })
    const navs = screen.getAllByRole('navigation', { name: 'Primary' })
    expect(navs).toHaveLength(2)
  })

  it('renders an unknown path as the 404 page', async () => {
    signInAs('STAFF')
    renderAt('/this-page-does-not-exist')
    expect(await screen.findByText('404')).toBeInTheDocument()
  })
})
