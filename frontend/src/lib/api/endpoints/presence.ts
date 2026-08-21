import { apiFetch } from '@/lib/api/client'
import type { PresenceVerificationRequest, PresenceVerificationResponse, QRChallengeResponse } from '@/lib/api/types'

/** MANAGER / TENANT_ADMIN only — the backend, not this check, is what enforces that. */
export function createQrChallenge(signal?: AbortSignal): Promise<QRChallengeResponse> {
  return apiFetch<QRChallengeResponse>('/api/v1/presence/qr/challenge', { method: 'POST', signal })
}

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
