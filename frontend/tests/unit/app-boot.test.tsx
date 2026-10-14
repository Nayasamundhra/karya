import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { App } from '@/app/App'

describe('application boot', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('boots with no persisted session and lands on the public landing page', async () => {
    render(<App />)

    // Bootstrap (no refresh token in storage) resolves to "unauthenticated",
    // RequireAuth redirects, and the lazy-loaded login page's chunk resolves
    // — all of which is genuinely asynchronous, hence `findBy`.
    expect(await screen.findByRole('heading', { name: /attendance you can trust/i })).toBeInTheDocument()
  })

  it('renders no console-crashing error boundary fallback on a clean boot', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: /attendance you can trust/i })
    expect(screen.queryByText(/karya ran into an unexpected problem/i)).not.toBeInTheDocument()
  })
})
