import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UserMenu } from '@/components/layout/UserMenu'
import { applyTheme, getAppliedTheme, readStoredTheme, setTheme, THEME_STORAGE_KEY } from '@/lib/theme/theme'
import { useAuthStore } from '@/stores/authStore'
import { TestQueryProvider } from './helpers/testQueryClient'

/**
 * Light is the default for everyone and dark is strictly opt-in — the OS
 * `prefers-color-scheme` must never decide. (That is the bug this guards: a
 * user signed up on the fixed-light public pages and landed in a dark
 * dashboard because their OS was in dark mode.)
 */
describe('theme preference', () => {
  beforeEach(() => {
    localStorage.clear()
    applyTheme('light')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('defaults to light when nothing is stored', () => {
    expect(readStoredTheme()).toBe('light')
  })

  it('does not follow the OS colour scheme, even when the OS asks for dark', () => {
    const matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('dark'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    vi.stubGlobal('matchMedia', matchMedia)

    expect(readStoredTheme()).toBe('light')
    expect(getAppliedTheme()).toBe('light')
    // Nothing in the theme code may even consult the OS preference.
    expect(matchMedia).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('remembers an explicit dark choice, and removes the key again for light', () => {
    setTheme('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(readStoredTheme()).toBe('dark')

    setTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('treats a corrupt stored value as light', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'purple')
    expect(readStoredTheme()).toBe('light')
  })

  it('still applies the choice for the session when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(readStoredTheme()).toBe('light')
    setTheme('dark')
    expect(getAppliedTheme()).toBe('dark')
  })
})

describe('theme toggle in the user menu', () => {
  beforeEach(() => {
    localStorage.clear()
    applyTheme('light')
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
      accessToken: 'token',
      accessTokenExpiresAt: Date.now() + 15 * 60 * 1000,
    })
  })

  afterEach(() => {
    useAuthStore.getState().clearSession()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('switches to dark and back, remembering the choice', async () => {
    render(
      <TestQueryProvider>
        <MemoryRouter>
          <UserMenu />
        </MemoryRouter>
      </TestQueryProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: /riya sharma/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /dark mode/i }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')

    await userEvent.click(screen.getByRole('button', { name: /riya sharma/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /light mode/i }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
  })
})
