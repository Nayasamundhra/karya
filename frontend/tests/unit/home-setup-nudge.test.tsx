import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import HomePage from '@/pages/HomePage'
import * as tenantApi from '@/lib/api/endpoints/tenant'
import * as usersApi from '@/lib/api/endpoints/users'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/tenant')
vi.mock('@/lib/api/endpoints/users')

function renderHome() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

function signInAsAdmin() {
  useAuthStore.setState({
    status: 'authenticated',
    user: {
      id: 'user-1',
      tenant_id: 'tenant-1',
      employee_code: 'ADMIN-1',
      name: 'Ada',
      email: 'ada@acme.com',
      role: 'TENANT_ADMIN',
      status: 'ACTIVE',
    },
    accessToken: 'test-token',
    accessTokenExpiresAt: Date.now() + 15 * 60 * 1000,
  })
}

const READY_LOCATION = {
  id: 'loc-1',
  name: 'HQ',
  description: null,
  latitude: 12.9,
  longitude: 77.5,
  geofence_radius_meters: 150,
  max_shift_hours: 16,
  status: 'ACTIVE' as const,
  qr_token: '11111111-1111-1111-1111-111111111111',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('HomePage setup nudge (TENANT_ADMIN only)', () => {
  afterEach(() => {
    useAuthStore.getState().clearSession()
    vi.mocked(tenantApi.getOwnLocation).mockReset()
    vi.mocked(usersApi.listUsers).mockReset()
  })

  it('nudges an admin toward the setup checklist while setup is incomplete', async () => {
    signInAsAdmin()
    vi.mocked(tenantApi.getOwnLocation).mockResolvedValue(READY_LOCATION)
    vi.mocked(usersApi.listUsers).mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 2, total: 1, total_pages: 1 },
    })
    renderHome()

    expect(await screen.findByText(/finish setting up your organization/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view checklist/i })).toHaveAttribute('href', '/setup')
  })

  it('shows no nudge once every setup step is done', async () => {
    signInAsAdmin()
    vi.mocked(tenantApi.getOwnLocation).mockResolvedValue(READY_LOCATION)
    vi.mocked(usersApi.listUsers).mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 2, total: 2, total_pages: 1 },
    })
    renderHome()

    await screen.findByRole('heading', { name: /welcome, ada/i })
    expect(screen.queryByText(/finish setting up your organization/i)).not.toBeInTheDocument()
  })
})
