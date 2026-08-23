import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import EmployeeDetailPage from '@/pages/manager/EmployeeDetailPage'
import type { AttendanceHistoryResponse, AttendanceTodayResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

const { getUserAttendance, getUserHistory } = vi.hoisted(() => ({
  getUserAttendance: vi.fn(),
  getUserHistory: vi.fn(),
}))

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()),
  getUserAttendance,
  getUserHistory,
}))

function emptyHistory(overrides: Partial<AttendanceHistoryResponse> = {}): AttendanceHistoryResponse {
  return {
    user_id: 'user-1',
    from_date: '2026-07-24',
    to_date: '2026-08-22',
    items: [],
    pagination: { page: 1, page_size: 30, total: 0, total_pages: 0 },
    ...overrides,
  }
}

function renderDetailPage(userId = 'user-1') {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={[`/team/${userId}`]}>
        <Routes>
          <Route path="/team/:userId" element={<EmployeeDetailPage />} />
        </Routes>
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

describe('EmployeeDetailPage', () => {
  afterEach(() => {
    getUserAttendance.mockReset()
    getUserHistory.mockReset()
  })

  it('shows the employee\'s current-day status and times', async () => {
    const today: AttendanceTodayResponse = {
      user_id: 'user-1',
      state: 'CHECKED_IN',
      day: {
        date: '2026-08-22',
        status: 'CHECKED_IN',
        sessions: [],
        first_check_in: '2026-08-22T09:04:00Z',
        last_check_out: null,
      },
    }
    getUserAttendance.mockResolvedValue(today)
    getUserHistory.mockResolvedValue(emptyHistory())

    renderDetailPage()

    expect(await screen.findByText('Checked in')).toBeInTheDocument()
    expect(screen.getByText(/checked in at/i)).toBeInTheDocument()
  })

  it('shows a "no attendance history available" empty state', async () => {
    getUserAttendance.mockResolvedValue({
      user_id: 'user-1',
      state: 'NOT_CHECKED_IN',
      day: { date: '2026-08-22', status: 'NO_RECORD', sessions: [], first_check_in: null, last_check_out: null },
    })
    getUserHistory.mockResolvedValue(emptyHistory())

    renderDetailPage()

    expect(await screen.findByText('No attendance history available')).toBeInTheDocument()
  })

  it('renders history days with pagination controls when there is more than one page', async () => {
    getUserAttendance.mockResolvedValue({
      user_id: 'user-1',
      state: 'NOT_CHECKED_IN',
      day: { date: '2026-08-22', status: 'NO_RECORD', sessions: [], first_check_in: null, last_check_out: null },
    })
    getUserHistory.mockResolvedValue(
      emptyHistory({
        items: [
          {
            date: '2026-08-21',
            status: 'COMPLETED',
            sessions: [],
            first_check_in: '2026-08-21T09:00:00Z',
            last_check_out: '2026-08-21T17:00:00Z',
          },
        ],
        pagination: { page: 1, page_size: 1, total: 2, total_pages: 2 },
      }),
    )

    renderDetailPage()

    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('shows a not-found error the same way for an unknown or cross-tenant employee id', async () => {
    const { ApiError } = await import('@/lib/api/errors')
    getUserAttendance.mockRejectedValue(new ApiError({ kind: 'not_found', message: 'User not found', status: 404 }))
    getUserHistory.mockResolvedValue(emptyHistory())

    renderDetailPage('does-not-exist')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/user not found/i)
  })
})
