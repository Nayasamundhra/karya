import { apiFetch } from '@/lib/api/client'
import type {
  EmailVerificationRequest,
  ResendVerificationRequest,
  ResendVerificationResponse,
  TenantOnboardingRequest,
  TenantOnboardingResponse,
  TokenResponse,
} from '@/lib/api/types'

/** Public - no access token exists yet. Throws `conflict` if the slug is taken. */
export function createTenant(payload: TenantOnboardingRequest): Promise<TenantOnboardingResponse> {
  return apiFetch<TenantOnboardingResponse>('/api/v1/onboarding/tenants', {
    method: 'POST',
    body: payload,
    auth: false,
  })
}

/** Public. Throws `unauthorized` if the token is invalid, expired, or already used. */
export function verifyEmail(payload: EmailVerificationRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/onboarding/verify-email', {
    method: 'POST',
    body: payload,
    auth: false,
  })
}

/**
 * Public. Always resolves with the same generic message, whether or not an
 * account actually existed to resend for — see the backend's own docstring
 * (`app.services.onboarding.service.resend_verification_email`). Throws an
 * `ApiError` with `kind: 'unavailable'` only if the mail server itself is
 * unreachable, never to signal "no such account".
 */
export function resendVerification(
  payload: ResendVerificationRequest,
): Promise<ResendVerificationResponse> {
  return apiFetch<ResendVerificationResponse>('/api/v1/onboarding/resend-verification', {
    method: 'POST',
    body: payload,
    auth: false,
  })
}
