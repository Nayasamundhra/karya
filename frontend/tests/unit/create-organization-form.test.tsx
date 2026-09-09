import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CreateOrganizationForm } from '@/features/onboarding/CreateOrganizationForm'
import { ApiError } from '@/lib/api/errors'
import * as onboardingApi from '@/lib/api/endpoints/onboarding'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/onboarding')

function renderForm() {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={['/onboarding']}>
        <CreateOrganizationForm />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

async function fillValidForm() {
  await userEvent.type(screen.getByLabelText(/organization name/i), 'Acme Technologies')
  await userEvent.type(screen.getByLabelText(/organization id/i), 'acme')
  await userEvent.type(screen.getByLabelText(/your name/i), 'Ada Lovelace')
  await userEvent.type(screen.getByLabelText(/your email/i), 'ada@acme.com')
  await userEvent.type(screen.getByLabelText(/password/i), 'correct-horse-battery-staple')
}

describe('CreateOrganizationForm', () => {
  afterEach(() => {
    vi.mocked(onboardingApi.createTenant).mockReset()
  })

  it('validates required fields before calling the API', async () => {
    renderForm()
    await userEvent.click(screen.getByRole('button', { name: /create organization/i }))

    expect(await screen.findByText(/organization name is required/i)).toBeInTheDocument()
    expect(onboardingApi.createTenant).not.toHaveBeenCalled()
  })

  it('rejects an organization ID with disallowed characters, client-side', async () => {
    renderForm()
    await fillValidForm()
    await userEvent.clear(screen.getByLabelText(/organization id/i))
    await userEvent.type(screen.getByLabelText(/organization id/i), 'has a space')
    await userEvent.click(screen.getByRole('button', { name: /create organization/i }))

    expect(await screen.findByText(/lowercase letters, numbers and hyphens only/i)).toBeInTheDocument()
    expect(onboardingApi.createTenant).not.toHaveBeenCalled()
  })

  it('submits and shows a check-your-email confirmation on success', async () => {
    vi.mocked(onboardingApi.createTenant).mockResolvedValue({
      organization_slug: 'acme',
      message: 'Check your email to verify your account before signing in.',
    })
    renderForm()
    await fillValidForm()
    await userEvent.click(screen.getByRole('button', { name: /create organization/i }))

    expect(await screen.findByText(/check your email/i)).toBeInTheDocument()
    expect(onboardingApi.createTenant).toHaveBeenCalledWith({
      organization_name: 'Acme Technologies',
      organization_slug: 'acme',
      admin_name: 'Ada Lovelace',
      admin_email: 'ada@acme.com',
      admin_password: 'correct-horse-battery-staple',
    })
  })

  it('attaches a taken-slug conflict to the organization ID field, not a form-level banner', async () => {
    vi.mocked(onboardingApi.createTenant).mockRejectedValue(
      new ApiError({ kind: 'conflict', message: 'That organization ID is already in use', status: 409 }),
    )
    renderForm()
    await fillValidForm()
    await userEvent.click(screen.getByRole('button', { name: /create organization/i }))

    // Attached to the field itself...
    const slugInput = await screen.findByLabelText(/organization id/i)
    expect(slugInput).toHaveAccessibleDescription(/already in use/i)
    // ...and exactly once — no separate top-of-form banner duplicating it.
    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })
})
