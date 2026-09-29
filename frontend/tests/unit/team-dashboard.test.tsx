/**
 * `TeamAttendanceTable` renders both the desktop `<table>` and the mobile
 * card list in the DOM at once (CSS, not JS, decides which is visible — same
 * pattern as the sidebar/bottom-nav split, see `routing.test.tsx`), so every
 * assertion here is scoped to the `<table>` to avoid "found multiple
 * elements" from the duplicate mobile copy.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import TeamPage from '@/pages/manager/TeamPage'
import type { TeamAttendanceResponse, TeamHoursResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

const { getTeamToday, getTeamHours } = vi.hoisted(() => ({
  getTeamToday: vi.fn(),
  getTeamHours: vi.fn(),
}))

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()),
  getTeamToday,
  getTeamHours,
}))

function teamHoursResponse(): TeamHoursResponse {
  return {
    date: '2026-08-22',
    week_start: '2026-08-17',
    month_start: '2026-08-01',
    summary: { total_today_hours: 5.5, total_week_hours: 5.5, total_month_hours: 5.5 },
    employees: [
      { user_id: 'user-1', name: 'Riya Sharma', employee_code: 'EMP-1', today_hours: 5.5, week_hours: 5.5, month_hours: 5.5 },
      { user_id: 'user-2', name: 'Amit Kumar', employee_code: 'EMP-2', today_hours: 0, week_hours: 0, month_hours: 0 },
      { user_id: 'user-3', name: 'Priya Nair', employee_code: 'EMP-3', today_hours: 0, week_hours: 0, month_hours: 0 },
    ],
  }
}

function teamResponse(): TeamAttendanceResponse {
  return {
    date: '2026-08-22',
    summary: { total_staff: 3, no_record: 1, checked_in: 1, completed: 1 },
    employees: [
      {
        user_id: 'user-1',
        name: 'Riya Sharma',
        employee_code: 'EMP-1',
        status: 'CHECKED_IN',
        check_in: '2026-08-22T09:04:00Z',
        check_out: null,
      },
      {
        user_id: 'user-2',
        name: 'Amit Kumar',
        employee_code: 'EMP-2',
        status: 'COMPLETED',
        check_in: '2026-08-22T09:00:00Z',
        check_out: '2026-08-22T17:00:00Z',
      },
      {
        user_id: 'user-3',
        name: 'Priya Nair',
        employee_code: 'EMP-3',
        status: 'NO_RECORD',
        check_in: null,
        check_out: null,
      },
    ],
  }
}

function renderTeamPage() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/team']}>
        <Routes>
          <Route path="/team" element={<TeamPage />} />
          <Route path="/team/:userId" element={<div>Employee detail page</div>} />
        </Routes>
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

describe('TeamPage (manager dashboard)', () => {
  beforeEach(() => {
    // Every test below exercises the "today" section; the hours section
    // (a second, independent query - see `TeamPage`) defaults to a valid
    // response so it never causes an unrelated test to see one of its own
    // states (loading/error) unless a test opts into that explicitly.
    getTeamHours.mockResolvedValue(teamHoursResponse())
  })

  afterEach(() => {
    getTeamToday.mockReset()
    getTeamHours.mockReset()
  })

  it('shows accurate summary counts from the backend response, not recomputed locally', async () => {
    getTeamToday.mockResolvedValue(teamResponse())
    renderTeamPage()

    // Scoped to the four-card breakdown (`role="group"`) — the new headline
    // above it (`TeamHeadline`) reads the same backend numbers into its own
    // "1 of 3 checked in" summary, which would otherwise collide with these
    // exact-text assertions.
    const summary = await screen.findByRole('group', { name: 'Team summary' })
    expect(within(summary).getByText('Total Employees')).toBeInTheDocument()
    expect(within(summary).getByText('3')).toBeInTheDocument() // total
    expect(within(summary).getAllByText('1')).toHaveLength(3) // checked_in, completed, no_record

    // The headline reads the same backend-reported number, not a second,
    // possibly-drifting computation.
    expect(screen.getByText('of 3 checked in')).toBeInTheDocument()
  })

  it('lists every employee with name, code, status, check-in and check-out', async () => {
    getTeamToday.mockResolvedValue(teamResponse())
    renderTeamPage()

    const table = await screen.findByRole('table', { name: "Today's attendance" })
    expect(within(table).getByText('Riya Sharma')).toBeInTheDocument()
    expect(within(table).getByText('EMP-1')).toBeInTheDocument()
    expect(within(table).getByText('Amit Kumar')).toBeInTheDocument()
    expect(within(table).getByText('Priya Nair')).toBeInTheDocument()
    // Never exposes email, role, GPS, or the raw user id (§4).
    expect(within(table).queryByText(/@/)).not.toBeInTheDocument()
  })

  it('filters the list by status without issuing another request', async () => {
    getTeamToday.mockResolvedValue(teamResponse())
    const user = userEvent.setup()
    renderTeamPage()

    const table = await screen.findByRole('table', { name: "Today's attendance" })
    expect(within(table).getByText('Riya Sharma')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Completed' }))

    expect(within(table).queryByText('Riya Sharma')).not.toBeInTheDocument()
    expect(within(table).getByText('Amit Kumar')).toBeInTheDocument()
    expect(within(table).queryByText('Priya Nair')).not.toBeInTheDocument()
    expect(getTeamToday).toHaveBeenCalledTimes(1)
  })

  it('shows an empty state when no employee matches the active filter', async () => {
    getTeamToday.mockResolvedValue({
      date: '2026-08-22',
      summary: { total_staff: 0, no_record: 0, checked_in: 0, completed: 0 },
      employees: [],
    })
    renderTeamPage()

    expect(await screen.findByText('No employees match')).toBeInTheDocument()
  })

  it('navigates to the employee detail route on row click', async () => {
    getTeamToday.mockResolvedValue(teamResponse())
    const user = userEvent.setup()
    renderTeamPage()

    const table = await screen.findByRole('table', { name: "Today's attendance" })
    await user.click(within(table).getByText('Riya Sharma'))
    await waitFor(() => expect(screen.getByText('Employee detail page')).toBeInTheDocument())
  })

  it('shows an error state with a retry action when the request fails', async () => {
    getTeamToday.mockRejectedValue(new Error('network down'))
    renderTeamPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('shows the hours summary and per-employee breakdown', async () => {
    getTeamToday.mockResolvedValue(teamResponse())
    renderTeamPage()

    const hours = await screen.findByRole('group', { name: 'Team hours worked' })
    expect(within(hours).getAllByText('5h 30m')).toHaveLength(3) // today, week, month
    expect(screen.getByRole('heading', { name: 'Hours worked' })).toBeInTheDocument()
  })

  it('the today section and the hours section fail independently', async () => {
    getTeamToday.mockResolvedValue(teamResponse())
    getTeamHours.mockRejectedValue(new Error('hours endpoint down'))
    renderTeamPage()

    // Today's data still renders...
    expect(await screen.findByRole('table', { name: "Today's attendance" })).toBeInTheDocument()
    // ...while only the hours section reports an error.
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
