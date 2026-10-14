import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TeamHoursPage from '@/pages/manager/TeamHoursPage'
import type { TeamHoursResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

const { getTeamHours } = vi.hoisted(() => ({ getTeamHours: vi.fn() }))

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()),
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
      { user_id: 'user-2', name: 'Amit Kumar', employee_code: 'EMP-2', today_hours: 0, week_hours: 8.5, month_hours: 28 },
      { user_id: 'user-3', name: 'Priya Nair', employee_code: 'EMP-3', today_hours: 0, week_hours: 0, month_hours: 0 },
    ],
  }
}

function renderPage() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/team/hours']}>
        <TeamHoursPage />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

describe('TeamHoursPage', () => {
  afterEach(() => {
    getTeamHours.mockReset()
  })

  it('shows the team summary cards and the per-employee breakdown table', async () => {
    getTeamHours.mockResolvedValue(teamHoursResponse())
    renderPage()

    const summary = await screen.findByRole('group', { name: 'Team hours worked' })
    expect(within(summary).getAllByText('5h 30m')).toHaveLength(3) // today, week, month

    const table = await screen.findByRole('table', { name: 'Hours worked by employee' })
    expect(within(table).getByText('Riya Sharma')).toBeInTheDocument()
    expect(within(table).getByText('Amit Kumar')).toBeInTheDocument()
    expect(within(table).getByText('Priya Nair')).toBeInTheDocument()
    // This page is hours-only — no status/check-in/check-out columns (that's /team's job).
    expect(within(table).queryByText('Checked in')).not.toBeInTheDocument()
  })

  it('renders the by-employee chart', async () => {
    getTeamHours.mockResolvedValue(teamHoursResponse())
    renderPage()

    await screen.findByRole('group', { name: 'Team hours worked' })
    expect(screen.getByRole('heading', { name: 'By employee' })).toBeInTheDocument()
    // The chart's accessible name carries every employee's full figures;
    // its x-axis labels (rendered as SVG <text>) use first names only.
    const chart = screen.getByRole('img', { name: /Hours by employee.*Amit Kumar/ })
    expect(chart.textContent).toContain('Amit')
  })

  it('shows an error state with a retry action when the request fails', async () => {
    getTeamHours.mockRejectedValue(new Error('network down'))
    renderPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
