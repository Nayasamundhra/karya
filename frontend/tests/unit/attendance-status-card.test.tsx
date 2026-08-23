import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AttendanceStatusCard } from '@/features/attendance/AttendanceStatusCard'
import type { AttendanceTodayResponse } from '@/lib/api/types'

function today(overrides: Partial<AttendanceTodayResponse['day']>, state: AttendanceTodayResponse['state']) {
  const response: AttendanceTodayResponse = {
    user_id: 'user-1',
    state,
    day: {
      date: '2026-08-22',
      status: 'NO_RECORD',
      sessions: [],
      first_check_in: null,
      last_check_out: null,
      ...overrides,
    },
  }
  return response
}

function renderCard(response: AttendanceTodayResponse) {
  render(
    <MemoryRouter>
      <AttendanceStatusCard today={response} />
    </MemoryRouter>,
  )
}

describe('AttendanceStatusCard', () => {
  it('NO_RECORD: shows "Not checked in" with a primary Check in action', () => {
    renderCard(today({ status: 'NO_RECORD' }, 'NOT_CHECKED_IN'))

    expect(screen.getAllByText('Not checked in').length).toBeGreaterThan(0)
    const link = screen.getByRole('link', { name: /check in/i })
    expect(link).toHaveAttribute('href', '/attendance/check-in')
  })

  it('CHECKED_IN: shows "You\'re checked in", the check-in time, and a Check out action', () => {
    renderCard(today({ status: 'CHECKED_IN', first_check_in: '2026-08-22T09:04:00Z' }, 'CHECKED_IN'))

    expect(screen.getByText("You're checked in")).toBeInTheDocument()
    expect(screen.getByText(/checked in at/i)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /check out/i })
    expect(link).toHaveAttribute('href', '/attendance/check-out')
  })

  it('COMPLETED: shows "Attendance completed" with a de-emphasized "Check in again" action', () => {
    renderCard(
      today(
        { status: 'COMPLETED', first_check_in: '2026-08-22T09:04:00Z', last_check_out: '2026-08-22T17:30:00Z' },
        'NOT_CHECKED_IN',
      ),
    )

    expect(screen.getByText('Attendance completed')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /check in again/i })
    expect(link).toHaveAttribute('href', '/attendance/check-in')
  })

  it('never shows a Check out action while NOT_CHECKED_IN, even on a COMPLETED day', () => {
    renderCard(today({ status: 'COMPLETED' }, 'NOT_CHECKED_IN'))
    expect(screen.queryByRole('link', { name: /^check out$/i })).not.toBeInTheDocument()
  })
})
