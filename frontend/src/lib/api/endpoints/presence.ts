import { apiFetch } from '@/lib/api/client'
import type { PresenceVerificationRequest, PresenceVerificationResponse } from '@/lib/api/types'

/**
 * Verify GPS + QR evidence for the current user. A rejection is a normal
 * `200` response with `verified: false` — see `PresenceVerificationResponse`
 * — never thrown as an `ApiError`. Only a genuinely unprocessable request
 * (401, 422, network) reaches the caller as a throw.
 */
export function verifyPresence(
  payload: PresenceVerificationRequest,
  signal?: AbortSignal,
): Promise<PresenceVerificationResponse> {
  return apiFetch<PresenceVerificationResponse>('/api/v1/presence/verify', { method: 'POST', body: payload, signal })
}
