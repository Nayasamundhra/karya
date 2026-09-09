import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SetupChecklistPage from '@/pages/onboarding/SetupChecklistPage'
import { ApiError } from '@/lib/api/errors'
import * as tenantApi from '@/lib/api/endpoints/tenant'
import * as displayApi from '@/lib/api/endpoints/display'
import * as usersApi from '@/lib/api/endpoints/users'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/tenant')
vi.mock('@/lib/api/endpoints/display')
vi.mock('@/lib/api/endpoints/users')

function renderPage() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/setup']}>
        <SetupChecklistPage />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

function signIn() {
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

const NO_LOCATION = new ApiError({
  kind: 'not_found',
  message: 'No attendance location is configured yet',
  status: 404,
})

describe('SetupChecklistPage', () => {
  afterEach(() => {
    useAuthStore.getState().clearSession()
    vi.mocked(tenantApi.getOwnLocation).mockReset()
    vi.mocked(displayApi.listDisplayTokens).mockReset()
    vi.mocked(usersApi.listUsers).mockReset()
  })

  it('shows every step as outstanding, with an action, for a fresh tenant', async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockRejectedValue(NO_LOCATION)
    vi.mocked(displayApi.listDisplayTokens).mockResolvedValue({ items: [] })
    vi.mocked(usersApi.listUsers).mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 2, total: 1, total_pages: 1 },
    })
    renderPage()

    expect(await screen.findByText('Configure attendance location')).toBeInTheDocument()
    expect(screen.getByText('Set up an attendance display')).toBeInTheDocument()
    expect(screen.getByText('Add employees')).toBeInTheDocument()
    expect(
      screen.getAllByRole('link', { name: /set up location|create a display|manage employees/i }),
    ).toHaveLength(3)
    expect(screen.queryByText(/you're ready/i)).not.toBeInTheDocument()
  })

  it("shows the ready state once location, a display and an employee all exist", async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockResolvedValue({
      id: 'loc-1',
      name: 'HQ',
      description: null,
      latitude: 12.9,
      longitude: 77.5,
      geofence_radius_meters: 150,
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    vi.mocked(displayApi.listDisplayTokens).mockResolvedValue({
      items: [
        {
          id: 'disp-1',
          label: 'Lobby',
          created_at: '2026-01-01T00:00:00Z',
          last_used_at: null,
          revoked_at: null,
        },
      ],
    })
    vi.mocked(usersApi.listUsers).mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 2, total: 2, total_pages: 1 },
    })
    renderPage()

    expect(await screen.findByText(/you're ready/i)).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: /set up location|create a display|manage employees/i }),
    ).not.toBeInTheDocument()
  })
})
