import { apiFetch } from '@/lib/api/client'
import type {
  DisplayTokenCreateRequest,
  DisplayTokenCreateResponse,
  DisplayTokenListResponse,
  DisplayTokenResponse,
  QRChallengeResponse,
} from '@/lib/api/types'

/** MANAGER / TENANT_ADMIN only. Throws `conflict` if no attendance location
 * has been set up yet. The returned `token` is shown exactly once. */
export function createDisplayToken(
  payload: DisplayTokenCreateRequest,
): Promise<DisplayTokenCreateResponse> {
  return apiFetch<DisplayTokenCreateResponse>('/api/v1/tenant/display-tokens', {
    method: 'POST',
    body: payload,
  })
}

/** MANAGER / TENANT_ADMIN only. Never includes a raw token. */
export function listDisplayTokens(signal?: AbortSignal): Promise<DisplayTokenListResponse> {
  return apiFetch<DisplayTokenListResponse>('/api/v1/tenant/display-tokens', { signal })
}

/** MANAGER / TENANT_ADMIN only. */
export function revokeDisplayToken(displayTokenId: string): Promise<DisplayTokenResponse> {
  return apiFetch<DisplayTokenResponse>(
    `/api/v1/tenant/display-tokens/${displayTokenId}/revoke`,
    { method: 'POST' },
  )
}

/**
 * A kiosk revokes its own credential - authenticated by the display token
 * itself, exactly like `createQrChallengeForDisplay` below, never a signed-in
 * user's session. This is what backs the "Reset this display" control
 * (`src/pages/display/KioskPage.tsx`): resetting a kiosk now disables its
 * old token server-side, not just the copy stored in this browser.
 */
export function revokeSelf(displayToken: string): Promise<DisplayTokenResponse> {
  return apiFetch<DisplayTokenResponse>('/api/v1/display/revoke-self', {
    method: 'POST',
    token: displayToken,
    auth: false,
  })
}

/**
 * Mint a QR challenge as an office-display kiosk - authenticated by the
 * kiosk's own display token, never a signed-in user's session. See
 * `src/lib/api/client.ts`'s `token` option and `src/features/display/`.
 */
export function createQrChallengeForDisplay(
  displayToken: string,
  signal?: AbortSignal,
): Promise<QRChallengeResponse> {
  return apiFetch<QRChallengeResponse>('/api/v1/presence/qr/challenge/display', {
    method: 'POST',
    token: displayToken,
    auth: false,
    signal,
  })
}
