import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LoginForm } from '@/features/auth/LoginForm'
import { ApiError } from '@/lib/api/errors'
import * as authSession from '@/lib/auth/session'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/auth/session', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth/session')>()
  return { ...actual, login: vi.fn() }
})

function renderForm() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/login']}>
        <LoginForm />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

describe('LoginForm', () => {
  afterEach(() => {
    vi.mocked(authSession.login).mockReset()
  })

  it('validates required fields before calling the API', async () => {
    renderForm()
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/enter your organization id/i)).toBeInTheDocument()
    expect(screen.getByText(/enter your email/i)).toBeInTheDocument()
    expect(authSession.login).not.toHaveBeenCalled()
  })

  it('shows a loading label and calls login with the entered credentials', async () => {
    let resolveLogin: () => void = () => {}
    vi.mocked(authSession.login).mockImplementation(
      () => new Promise((resolve) => (resolveLogin = () => resolve(undefined))),
    )
    renderForm()

    await userEvent.type(screen.getByLabelText(/organization id/i), 'acme')
    await userEvent.type(screen.getByLabelText(/email/i), 'riya@acme.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('button', { name: /signing in/i })).toBeDisabled()
    expect(vi.mocked(authSession.login).mock.calls[0]?.[0]).toEqual({
      tenantSlug: 'acme',
      email: 'riya@acme.com',
      password: 'correct-horse-battery',
    })
    resolveLogin()
  })

  it('shows a generic alert on invalid credentials, without naming which field was wrong', async () => {
    vi.mocked(authSession.login).mockRejectedValue(
      new ApiError({ kind: 'unauthorized', message: 'Invalid credentials', status: 401 }),
    )
    renderForm()

    await userEvent.type(screen.getByLabelText(/organization id/i), 'acme')
    await userEvent.type(screen.getByLabelText(/email/i), 'riya@acme.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid credentials/i)
    expect(screen.queryByText(/email/i, { selector: 'p' })).not.toBeInTheDocument()
  })

  it('surfaces a rate-limit rejection with a wait-and-retry message', async () => {
    vi.mocked(authSession.login).mockRejectedValue(
      new ApiError({ kind: 'rate_limited', message: 'Too many requests', status: 429, retryAfterSeconds: 42 }),
    )
    renderForm()

    await userEvent.type(screen.getByLabelText(/organization id/i), 'acme')
    await userEvent.type(screen.getByLabelText(/email/i), 'riya@acme.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'whatever123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/wait about 42s/i))
  })
})
