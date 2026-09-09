import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { KioskDisplay } from '@/features/display/KioskDisplay'
import { ApiError } from '@/lib/api/errors'
import * as displayApi from '@/lib/api/endpoints/display'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/display')

function renderKiosk(props: { onInvalidToken?: () => void } = {}) {
  return render(
    <TestQueryProvider>
      <KioskDisplay displayToken="raw-display-token" onInvalidToken={props.onInvalidToken ?? vi.fn()} />
    </TestQueryProvider>,
  )
}

describe('KioskDisplay', () => {
  afterEach(() => {
    vi.mocked(displayApi.createQrChallengeForDisplay).mockReset()
  })

  it('renders a scannable QR image once a challenge is minted, and counts down to the next refresh', async () => {
    vi.mocked(displayApi.createQrChallengeForDisplay).mockResolvedValue({
      challenge_id: 'challenge-1',
      nonce: 'nonce-1',
      expires_at: new Date(Date.now() + 30_000).toISOString(),
      expires_in: 30,
    })
    const { container } = renderKiosk()

    // `alt=""` deliberately removes this from the accessibility tree (a
    // screen-reader user cannot scan it either way — see the component) —
    // query the element directly rather than by role.
    const img = await waitFor(() => {
      const el = container.querySelector('img')
      if (!el) throw new Error('QR image not rendered yet')
      return el
    })
    expect(img).toHaveAttribute('src', expect.stringContaining('data:image/png;base64,'))
    // The countdown is cosmetic and server-driven (§10's "Refreshing in 18
    // seconds") — real timers tick during the QR image's async render, so
    // this checks the shape rather than pinning an exact second.
    expect(await screen.findByText(/^refreshing in \d+s$/i)).toBeInTheDocument()
    // No employee/tenant identity of any kind is rendered on this screen.
    expect(screen.queryByText(/acme/i)).not.toBeInTheDocument()
  })

  it('shows an offline-style status and calls back on an unauthorized (revoked) token', async () => {
    const onInvalidToken = vi.fn()
    vi.mocked(displayApi.createQrChallengeForDisplay).mockRejectedValue(
      new ApiError({ kind: 'unauthorized', message: 'Not authenticated', status: 401 }),
    )
    renderKiosk({ onInvalidToken })

    // The hook retries transient-looking failures twice before settling
    // into `isError` (real backoff delay), so this needs more than the
    // default `waitFor` timeout.
    await waitFor(() => expect(onInvalidToken).toHaveBeenCalled(), { timeout: 8_000 })
  })
})
