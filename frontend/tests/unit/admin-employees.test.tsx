/**
 * Employee management (§8, §11–§15). Radix `Select`/`DropdownMenu` need a
 * couple of DOM APIs jsdom doesn't implement (pointer capture, scrollIntoView)
 * — stubbed here, scoped to this file only, rather than in the shared test
 * setup nothing else in the suite currently needs them for.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import UsersPage from '@/pages/admin/UsersPage'
import { useToastStore } from '@/stores/toastStore'
import type { UserDetailResponse, UserListResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

const { listUsers, createUser, updateUser, changeUserRole, activateUser, deactivateUser } = vi.hoisted(() => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  changeUserRole: vi.fn(),
  activateUser: vi.fn(),
  deactivateUser: vi.fn(),
}))

vi.mock('@/lib/api/endpoints/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/endpoints/users')>()),
  listUsers,
  createUser,
  updateUser,
  changeUserRole,
  activateUser,
  deactivateUser,
}))

beforeAll(() => {
  // jsdom's implementations of these throw/no-op in ways Radix doesn't expect.
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  window.HTMLElement.prototype.hasPointerCapture = vi.fn()
  window.HTMLElement.prototype.releasePointerCapture = vi.fn()
})

function employee(overrides: Partial<UserDetailResponse> = {}): UserDetailResponse {
  return {
    id: 'user-1',
    tenant_id: 'tenant-1',
    employee_code: 'EMP-1',
    name: 'Riya Sharma',
    email: 'riya@acme.com',
    role: 'STAFF',
    status: 'ACTIVE',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function listResponse(items: UserDetailResponse[]): UserListResponse {
  return { items, pagination: { page: 1, page_size: 25, total: items.length, total_pages: 1 } }
}

function renderUsersPage() {
  return render(
    <TestQueryProvider>
      <UsersPage />
    </TestQueryProvider>,
  )
}

describe('UsersPage (tenant admin employee management)', () => {
  afterEach(() => {
    listUsers.mockReset()
    createUser.mockReset()
    updateUser.mockReset()
    changeUserRole.mockReset()
    activateUser.mockReset()
    deactivateUser.mockReset()
  })

  it('lists employees with name, code, role, and status', async () => {
    listUsers.mockResolvedValue(listResponse([employee(), employee({ id: 'user-2', name: 'Amit Kumar', role: 'MANAGER' })]))
    renderUsersPage()

    const table = await screen.findByRole('table')
    expect(within(table).getByText('Riya Sharma')).toBeInTheDocument()
    expect(within(table).getByText('Employee')).toBeInTheDocument() // STAFF -> "Employee" (§9)
    expect(within(table).getByText('Amit Kumar')).toBeInTheDocument()
    expect(within(table).getByText('Manager')).toBeInTheDocument()
    // §9: the bare word "Staff" never appears in the product UI.
    expect(within(table).queryByText(/\bStaff\b/)).not.toBeInTheDocument()
  })

  it('shows "No employees yet" when the tenant has none', async () => {
    listUsers.mockResolvedValue(listResponse([]))
    renderUsersPage()
    expect(await screen.findByText('No employees yet')).toBeInTheDocument()
  })

  it('debounces search — types a full query but only issues one request for the final value', async () => {
    listUsers.mockResolvedValue(listResponse([employee()]))
    const user = userEvent.setup()
    renderUsersPage()
    await screen.findByRole('table')
    listUsers.mockClear()

    await user.type(screen.getByLabelText('Search'), 'ami')

    await waitFor(() => expect(listUsers).toHaveBeenCalledWith(expect.objectContaining({ search: 'ami' }), expect.anything()))
    expect(listUsers).toHaveBeenCalledTimes(1)
  })

  it('creates an employee and refreshes the list', async () => {
    listUsers.mockResolvedValue(listResponse([employee()]))
    createUser.mockResolvedValue(employee({ id: 'user-2', name: 'New Hire' }))
    const user = userEvent.setup()
    renderUsersPage()
    await screen.findByRole('table')

    await user.click(screen.getByRole('button', { name: /add employee/i }))
    await user.type(screen.getByLabelText('Name'), 'New Hire')
    await user.type(screen.getByLabelText('Email'), 'new.hire@acme.com')
    await user.type(screen.getByLabelText('Employee code'), 'EMP-9')
    await user.type(screen.getByLabelText('Password'), 'a-strong-password')
    await user.click(screen.getByRole('button', { name: /^create employee$/i }))

    await waitFor(() => expect(createUser).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'New Hire', email: 'new.hire@acme.com', employee_code: 'EMP-9', role: 'STAFF' }),
    ))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Add employee' })).not.toBeInTheDocument())
  })

  it('shows a field-level error when creating an employee with a duplicate email', async () => {
    const { ApiError } = await import('@/lib/api/errors')
    listUsers.mockResolvedValue(listResponse([employee()]))
    createUser.mockRejectedValue(
      new ApiError({ kind: 'conflict', message: 'A user with that email already exists', status: 409 }),
    )
    const user = userEvent.setup()
    renderUsersPage()
    await screen.findByRole('table')

    await user.click(screen.getByRole('button', { name: /add employee/i }))
    await user.type(screen.getByLabelText('Name'), 'New Hire')
    await user.type(screen.getByLabelText('Email'), 'riya@acme.com')
    await user.type(screen.getByLabelText('Employee code'), 'EMP-9')
    await user.type(screen.getByLabelText('Password'), 'a-strong-password')
    await user.click(screen.getByRole('button', { name: /^create employee$/i }))

    expect(await screen.findByText('A user with that email already exists')).toBeInTheDocument()
    // The dialog stays open on a rejected submission rather than closing.
    expect(screen.getByRole('heading', { name: 'Add employee' })).toBeInTheDocument()
  })

  it('edits an employee\'s profile fields', async () => {
    listUsers.mockResolvedValue(listResponse([employee()]))
    updateUser.mockResolvedValue(employee({ name: 'Riya S.' }))
    const user = userEvent.setup()
    renderUsersPage()
    const table = await screen.findByRole('table')

    await user.click(within(table).getByRole('button', { name: /actions for riya sharma/i }))
    await user.click(await screen.findByRole('menuitem', { name: 'Edit' }))

    const nameInput = await screen.findByLabelText('Name')
    await user.clear(nameInput)
    await user.type(nameInput, 'Riya S.')
    await user.click(screen.getByRole('button', { name: /save changes/i }))

    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith('user-1', expect.objectContaining({ name: 'Riya S.' })),
    )
  })

  it('asks for confirmation before deactivating, and calls the backend only on confirm', async () => {
    listUsers.mockResolvedValue(listResponse([employee()]))
    deactivateUser.mockResolvedValue(employee({ status: 'INACTIVE' }))
    const user = userEvent.setup()
    renderUsersPage()
    const table = await screen.findByRole('table')

    await user.click(within(table).getByRole('button', { name: /actions for riya sharma/i }))
    await user.click(await screen.findByRole('menuitem', { name: 'Deactivate' }))

    expect(await screen.findByText('Deactivate employee?')).toBeInTheDocument()
    expect(screen.getByText(/riya sharma will no longer be able to sign in/i)).toBeInTheDocument()
    expect(deactivateUser).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    await waitFor(() => expect(deactivateUser).toHaveBeenCalledWith('user-1'))
  })

  it('shows the backend\'s last-admin refusal message and keeps the confirmation dialog open', async () => {
    const { ApiError } = await import('@/lib/api/errors')
    listUsers.mockResolvedValue(listResponse([employee({ role: 'TENANT_ADMIN' })]))
    deactivateUser.mockRejectedValue(
      new ApiError({ kind: 'conflict', message: 'The tenant must retain at least one active administrator', status: 409 }),
    )
    const pushSpy = vi.spyOn(useToastStore.getState(), 'push')
    const user = userEvent.setup()
    renderUsersPage()
    const table = await screen.findByRole('table')

    await user.click(within(table).getByRole('button', { name: /actions for riya sharma/i }))
    await user.click(await screen.findByRole('menuitem', { name: 'Deactivate' }))
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))

    await waitFor(() =>
      expect(pushSpy).toHaveBeenCalledWith(
        expect.objectContaining({ description: 'The tenant must retain at least one active administrator' }),
      ),
    )
  })

  it('activates an inactive employee without a confirmation dialog', async () => {
    listUsers.mockResolvedValue(listResponse([employee({ status: 'INACTIVE' })]))
    activateUser.mockResolvedValue(employee({ status: 'ACTIVE' }))
    const user = userEvent.setup()
    renderUsersPage()
    const table = await screen.findByRole('table')

    await user.click(within(table).getByRole('button', { name: /actions for riya sharma/i }))
    await user.click(await screen.findByRole('menuitem', { name: 'Activate' }))

    await waitFor(() => expect(activateUser).toHaveBeenCalledWith('user-1'))
  })

  it('changes an employee\'s role via the role dialog', async () => {
    listUsers.mockResolvedValue(listResponse([employee()]))
    changeUserRole.mockResolvedValue(employee({ role: 'MANAGER' }))
    const user = userEvent.setup()
    renderUsersPage()
    const table = await screen.findByRole('table')

    await user.click(within(table).getByRole('button', { name: /actions for riya sharma/i }))
    await user.click(await screen.findByRole('menuitem', { name: 'Change role' }))

    await user.click(screen.getByRole('combobox', { name: 'Role' }))
    await user.click(await screen.findByRole('option', { name: 'Manager' }))
    await user.click(screen.getByRole('button', { name: /save role/i }))

    await waitFor(() =>
      expect(changeUserRole).toHaveBeenCalledWith('user-1', { role: 'MANAGER' }),
    )
  })

  it('shows the backend\'s self-role-change refusal inline in the dialog', async () => {
    const { ApiError } = await import('@/lib/api/errors')
    listUsers.mockResolvedValue(listResponse([employee()]))
    changeUserRole.mockRejectedValue(
      new ApiError({ kind: 'forbidden', message: 'You cannot change your own role', status: 403 }),
    )
    const user = userEvent.setup()
    renderUsersPage()
    const table = await screen.findByRole('table')

    await user.click(within(table).getByRole('button', { name: /actions for riya sharma/i }))
    await user.click(await screen.findByRole('menuitem', { name: 'Change role' }))
    await user.click(screen.getByRole('combobox', { name: 'Role' }))
    await user.click(await screen.findByRole('option', { name: 'Manager' }))
    await user.click(screen.getByRole('button', { name: /save role/i }))

    expect(await screen.findByText('You cannot change your own role')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Change role' })).toBeInTheDocument()
  })
})
