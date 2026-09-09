import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AttendanceLocationCard } from '@/features/tenant/AttendanceLocationCard'
import { ApiError } from '@/lib/api/errors'
import * as tenantApi from '@/lib/api/endpoints/tenant'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/tenant')

function renderCard() {
  return render(
    <TestQueryProvider>
      <AttendanceLocationCard />
    </TestQueryProvider>,
  )
}

function signIn() {
  useAuthStore.setState({
    status: 'authenticated',
    user: {
      id: 'user-1',
      tenant_id: 'tenant-1',
      employee_code: 'ADM-1',
      name: 'Ada',
      email: 'ada@acme.com',
      role: 'TENANT_ADMIN',
      status: 'ACTIVE',
    },
    accessToken: 'test-token',
    accessTokenExpiresAt: Date.now() + 15 * 60 * 1000,
  })
}

describe('AttendanceLocationCard', () => {
  afterEach(() => {
    useAuthStore.getState().clearSession()
    vi.mocked(tenantApi.getOwnLocation).mockReset()
    vi.mocked(tenantApi.createOwnLocation).mockReset()
  })

  it('shows a create form — not an error state — when none exists yet (404)', async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockRejectedValue(
      new ApiError({ kind: 'not_found', message: 'No attendance location is configured yet', status: 404 }),
    )
    renderCard()

    expect(await screen.findByText(/not set up yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create attendance location/i })).toBeInTheDocument()
    // Not the generic ErrorState copy — 404-as-"nothing here yet" is the
    // whole point of this hook, and must not read as a failed request.
    expect(screen.queryByText(/that item doesn't exist/i)).not.toBeInTheDocument()
  })

  it('shows an edit form pre-filled from the existing location', async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockResolvedValue({
      id: 'loc-1',
      name: 'Head Office',
      description: null,
      latitude: 12.9716,
      longitude: 77.5946,
      geofence_radius_meters: 150,
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    renderCard()

    expect(await screen.findByDisplayValue('Head Office')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /save changes/i })).toBeDisabled()
  })

  it('surfaces a genuine fetch failure as an error state, not a create form', async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockRejectedValue(
      new ApiError({ kind: 'server', message: 'boom', status: 500 }),
    )
    renderCard()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /create attendance location/i })).not.toBeInTheDocument()
  })

  it('creates a location and switches the button to "Save changes"', async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockRejectedValue(
      new ApiError({ kind: 'not_found', message: 'No attendance location is configured yet', status: 404 }),
    )
    vi.mocked(tenantApi.createOwnLocation).mockResolvedValue({
      id: 'loc-1',
      name: 'HQ',
      description: null,
      latitude: 12.9716,
      longitude: 77.5946,
      geofence_radius_meters: 150,
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    renderCard()
    await screen.findByText(/not set up yet/i)

    await userEvent.type(screen.getByLabelText(/location name/i), 'HQ')
    await userEvent.type(screen.getByLabelText(/latitude/i), '12.9716')
    await userEvent.type(screen.getByLabelText(/longitude/i), '77.5946')
    await userEvent.click(screen.getByRole('button', { name: /create attendance location/i }))

    expect(await screen.findByRole('button', { name: /save changes/i })).toBeInTheDocument()
    expect(tenantApi.createOwnLocation).toHaveBeenCalledWith({
      name: 'HQ',
      description: '',
      latitude: 12.9716,
      longitude: 77.5946,
      geofence_radius_meters: 150,
    })
  })

  it('submits an optional description alongside the rest of the form', async () => {
    signIn()
    vi.mocked(tenantApi.getOwnLocation).mockRejectedValue(
      new ApiError({ kind: 'not_found', message: 'No attendance location is configured yet', status: 404 }),
    )
    vi.mocked(tenantApi.createOwnLocation).mockResolvedValue({
      id: 'loc-1',
      name: 'HQ',
      description: '3rd floor, Brigade Towers',
      latitude: 12.9716,
      longitude: 77.5946,
      geofence_radius_meters: 150,
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    renderCard()
    await screen.findByText(/not set up yet/i)

    await userEvent.type(screen.getByLabelText(/location name/i), 'HQ')
    await userEvent.type(screen.getByLabelText(/description/i), '3rd floor, Brigade Towers')
    await userEvent.type(screen.getByLabelText(/latitude/i), '12.9716')
    await userEvent.type(screen.getByLabelText(/longitude/i), '77.5946')
    await userEvent.click(screen.getByRole('button', { name: /create attendance location/i }))

    await screen.findByRole('button', { name: /save changes/i })
    expect(tenantApi.createOwnLocation).toHaveBeenCalledWith(
      expect.objectContaining({ description: '3rd floor, Brigade Towers' }),
    )
  })
})
