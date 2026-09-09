/**
 * §23/§28: user-facing copy says "Employee", never "Staff" — the `STAFF`
 * role identifier itself is an unrelated backend/API contract detail (see
 * CLAUDE.md) and is deliberately not what this checks.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { AttendanceStatusCard } from '@/features/attendance/AttendanceStatusCard'
import HomePage from '@/pages/HomePage'
import TeamPage from '@/pages/manager/TeamPage'
import UsersPage from '@/pages/admin/UsersPage'
import { useAuthStore } from '@/stores/authStore'
import type { AttendanceTodayResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

const { getTeamToday, getMyAttendance, getMyHistory } = vi.hoisted(() => ({
  getTeamToday: vi.fn(),
  // HomePage's STAFF path (`EmployeeHome`) fetches live attendance data.
  getMyAttendance: vi.fn().mockResolvedValue({
    user_id: 'user-1',
    state: 'NOT_CHECKED_IN',
    day: { date: '2026-08-22', status: 'NO_RECORD', sessions: [], first_check_in: null, last_check_out: null },
  }),
  getMyHistory: vi.fn().mockResolvedValue({
    user_id: 'user-1',
    from_date: '2026-08-16',
    to_date: '2026-08-22',
    items: [],
    pagination: { page: 1, page_size: 7, total: 0, total_pages: 0 },
  }),
}))
const { listUsers } = vi.hoisted(() => ({ listUsers: vi.fn() }))
const { getOwnTenant } = vi.hoisted(() => ({
  getOwnTenant: vi.fn().mockResolvedValue({
    id: 'tenant-1',
    name: 'Acme Co',
    slug: 'acme',
    status: 'ACTIVE',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
}))

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()),
  getTeamToday,
  getMyAttendance,
  getMyHistory,
}))
vi.mock('@/lib/api/endpoints/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/users')>()),
  listUsers,
}))
vi.mock('@/lib/api/endpoints/tenant', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/tenant')>()),
  getOwnTenant,
}))

function rendersNoBareStaffWord(container: HTMLElement) {
  // Matches the standalone word "Staff" (case-sensitive on the capital, as
  // product copy would render it) but not substrings inside unrelated words.
  expect(container.textContent).not.toMatch(/\bStaff\b/)
}

describe('Employee terminology', () => {
  it('HomePage greets a STAFF-role user as "Employee", not "Staff"', async () => {
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

    expect(
      await screen.findByRole('heading', { name: /good (morning|afternoon|evening), riya/i }),
    ).toBeInTheDocument()
    // Drain EmployeeHome's mocked attendance/history queries within this
    // test's own act() boundary, rather than leaving them pending to
    // resolve during whichever test runs next (see routing.test.tsx).
    await screen.findByText(/checked in at|haven.t checked in/i)
    await screen.findByText('This week')
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

  it('the manager dashboard never says "Staff", including in the STAFF-status filter/badges', async () => {
    getTeamToday.mockResolvedValue({
      date: '2026-08-22',
      summary: { total_staff: 1, no_record: 1, checked_in: 0, completed: 0 },
      employees: [
        { user_id: 'user-1', name: 'Riya Sharma', employee_code: 'EMP-1', status: 'NO_RECORD', check_in: null, check_out: null },
      ],
    })

    const { container } = render(
      <TestQueryProvider>
        <MemoryRouter>
          <TeamPage />
        </MemoryRouter>
      </TestQueryProvider>,
    )

    await screen.findAllByText('Riya Sharma')
    rendersNoBareStaffWord(container)
  })

  it('the employee management page never says "Staff" — a STAFF-role row reads "Employee"', async () => {
    listUsers.mockResolvedValue({
      items: [
        {
          id: 'user-1',
          tenant_id: 'tenant-1',
          employee_code: 'EMP-1',
          name: 'Riya Sharma',
          email: 'riya@acme.com',
          role: 'STAFF',
          status: 'ACTIVE',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      pagination: { page: 1, page_size: 25, total: 1, total_pages: 1 },
    })

    const { container } = render(
      <TestQueryProvider>
        <MemoryRouter>
          <UsersPage />
        </MemoryRouter>
      </TestQueryProvider>,
    )

    await screen.findAllByText('Riya Sharma')
    expect(screen.getAllByText('Employee').length).toBeGreaterThan(0)
    rendersNoBareStaffWord(container)
  })
})
