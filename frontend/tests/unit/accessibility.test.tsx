import { render, screen } from '@testing-library/react'
import axe from 'axe-core'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { Alert } from '@/components/ui/Alert'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoginForm } from '@/features/auth/LoginForm'
import TeamPage from '@/pages/manager/TeamPage'
import UsersPage from '@/pages/admin/UsersPage'
import { TestQueryProvider } from './helpers/testQueryClient'

const { getTeamToday } = vi.hoisted(() => ({ getTeamToday: vi.fn() }))
const { listUsers } = vi.hoisted(() => ({ listUsers: vi.fn() }))

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()),
  getTeamToday,
}))
vi.mock('@/lib/api/endpoints/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/users')>()),
  listUsers,
}))

/**
 * jsdom has no real layout/paint engine, so rules that need actual computed
 * colors (`color-contrast`) are unreliable here and disabled — contrast for
 * this palette is checked by hand against WCAG 2.2 AA (see
 * `src/styles/index.css`'s header comment), and a real-browser check
 * belongs in the Playwright suite, not a jsdom unit test.
 */
async function expectNoAxeViolations(container: Element) {
  const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toHaveLength(0)
}

describe('accessibility', () => {
  it('the login form has no detectable accessibility violations', async () => {
    const { container } = render(
      <TestQueryProvider>
        <MemoryRouter>
          <LoginForm />
        </MemoryRouter>
      </TestQueryProvider>,
    )
    await expectNoAxeViolations(container)
  })

  it('core design-system primitives (Button, Input, Badge, Alert) have no detectable violations', async () => {
    const { container } = render(
      <div>
        <Button>Primary action</Button>
        <Button variant="secondary">Secondary action</Button>
        <Input label="Employee code" hint="As assigned by your administrator" />
        <Badge variant="success">Checked in</Badge>
        <Alert variant="danger" title="Something went wrong">
          Please try again.
        </Alert>
      </div>,
    )
    await expectNoAxeViolations(container)
  })

  it('the manager dashboard (summary cards, filters, table) has no detectable violations', async () => {
    getTeamToday.mockResolvedValue({
      date: '2026-08-22',
      summary: { total_staff: 2, no_record: 1, checked_in: 1, completed: 0 },
      employees: [
        {
          user_id: 'user-1',
          name: 'Riya Sharma',
          employee_code: 'EMP-1',
          status: 'CHECKED_IN',
          check_in: '2026-08-22T09:04:00Z',
          check_out: null,
        },
        { user_id: 'user-2', name: 'Amit Kumar', employee_code: 'EMP-2', status: 'NO_RECORD', check_in: null, check_out: null },
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
    await expectNoAxeViolations(container)
  })

  it('the employee management page (search, filters, table, row actions) has no detectable violations', async () => {
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
    await expectNoAxeViolations(container)
  })
})
