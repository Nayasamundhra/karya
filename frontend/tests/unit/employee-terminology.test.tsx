/**
 * §23/§28: user-facing copy says "Employee", never "Staff" — the `STAFF`
 * role identifier itself is an unrelated backend/API contract detail (see
 * CLAUDE.md) and is deliberately not what this checks.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AttendanceStatusCard } from '@/features/attendance/AttendanceStatusCard'
import HomePage from '@/pages/HomePage'
import { useAuthStore } from '@/stores/authStore'
import type { AttendanceTodayResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

function rendersNoBareStaffWord(container: HTMLElement) {
  // Matches the standalone word "Staff" (case-sensitive on the capital, as
  // product copy would render it) but not substrings inside unrelated words.
  expect(container.textContent).not.toMatch(/\bStaff\b/)
}

describe('Employee terminology', () => {
  it('HomePage greets a STAFF-role user as "Employee", not "Staff"', () => {
    useAuthStore.setState({
      status: 'authenticated',
      user: {
        id: 'user-1',
        tenant_id: 'tenant-1',
        employee_code: 'EMP-1',
        name: 'Riya Sharma',
        email: 'riya@acme.com',
        role: 'STAFF',
        status: 'ACTIVE',
      },
    })

    const { container } = render(
      <TestQueryProvider>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </TestQueryProvider>,
    )

    expect(screen.getByText(/signed in as employee/i)).toBeInTheDocument()
    rendersNoBareStaffWord(container)
  })

  it('the attendance status card never says "Staff" in any of its three states', () => {
    const base: AttendanceTodayResponse = {
      user_id: 'user-1',
      state: 'NOT_CHECKED_IN',
      day: { date: '2026-08-22', status: 'NO_RECORD', sessions: [], first_check_in: null, last_check_out: null },
    }

    for (const status of ['NO_RECORD', 'CHECKED_IN', 'COMPLETED'] as const) {
      const { container, unmount } = render(
        <MemoryRouter>
          <AttendanceStatusCard
            today={{
              ...base,
              state: status === 'CHECKED_IN' ? 'CHECKED_IN' : 'NOT_CHECKED_IN',
              day: { ...base.day, status },
            }}
          />
        </MemoryRouter>,
      )
      rendersNoBareStaffWord(container)
      unmount()
    }
  })
})
