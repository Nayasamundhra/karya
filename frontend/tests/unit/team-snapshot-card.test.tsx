import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import HomePage from '@/pages/HomePage'
import * as tenantApi from '@/lib/api/endpoints/tenant'
import type { TeamAttendanceResponse, TeamHoursResponse } from '@/lib/api/types'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

const { getTeamToday, getTeamHours } = vi.hoisted(() => ({
  getTeamToday: vi.fn(),
  getTeamHours: vi.fn(),
}))

vi.mock('@/lib/api/endpoints/tenant')
vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()),
  getTeamToday,
  getTeamHours,
}))

function renderHome() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

function signInAsManager() {
  useAuthStore.setState({
    status: 'authenticated',
    user: {
      id: 'user-1',
      tenant_id: 'tenant-1',
      employee_code: 'MGR-1',
      name: 'Priya Menon',
      email: 'priya@acme.com',
      role: 'MANAGER',
      status: 'ACTIVE',
    },
    accessToken: 'test-token',
    accessTokenExpiresAt: Date.now() + 15 * 60 * 1000,
  })
}

function teamTodayResponse(): TeamAttendanceResponse {
  return {
    date: '2026-08-22',
    summary: { total_staff: 3, no_record: 1, checked_in: 1, completed: 1 },
    employees: [],
  }
}

function teamHoursResponse(): TeamHoursResponse {
  return {
    date: '2026-08-22',
    week_start: '2026-08-17',
    month_start: '2026-08-01',
    summary: { total_today_hours: 5.5, total_week_hours: 12, total_month_hours: 38 },
    employees: [],
  }
}

describe('HomePage team snapshot (MANAGER/TENANT_ADMIN only)', () => {
  afterEach(() => {
    useAuthStore.getState().clearSession()
    getTeamToday.mockReset()
    getTeamHours.mockReset()
    vi.mocked(tenantApi.getOwnTenant).mockReset()
  })

  it('shows a compact checked-in count and hours summary, linking to the full pages', async () => {
    signInAsManager()
    vi.mocked(tenantApi.getOwnTenant).mockResolvedValue({
      id: 'tenant-1',
      name: 'Acme Co',
      slug: 'acme',
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    getTeamToday.mockResolvedValue(teamTodayResponse())
    getTeamHours.mockResolvedValue(teamHoursResponse())
    renderHome()

    expect(await screen.findByText('1 of 3 checked in today')).toBeInTheDocument()
    expect(screen.getByText('5h 30m today · 12h this week')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view team/i })).toHaveAttribute('href', '/team')
    expect(screen.getByRole('link', { name: /view hours/i })).toHaveAttribute('href', '/team/hours')
  })

  it('does not render the snapshot at all if either request fails', async () => {
    signInAsManager()
    vi.mocked(tenantApi.getOwnTenant).mockResolvedValue({
      id: 'tenant-1',
      name: 'Acme Co',
      slug: 'acme',
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    getTeamToday.mockRejectedValue(new Error('network down'))
    getTeamHours.mockResolvedValue(teamHoursResponse())
    renderHome()

    await screen.findByRole('heading', { name: "What's next" })
    // The section renders while the query is still pending, then withdraws
    // once it settles to an error — same "don't crowd the page with a
    // second error banner" behavior as WeekOverview's own supplementary chart.
    await waitFor(() => expect(screen.queryByText('Team snapshot')).not.toBeInTheDocument())
  })
})
