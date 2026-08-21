/**
 * Auth endpoints. `auth: false` on every call here — these are exactly the
 * calls that must not go through the authenticated-request/refresh-retry
 * path in `client.ts` (login and refresh don't have an access token yet by
 * definition, and refresh/logout carry the refresh token as a request body
 * field, never as a bearer header).
 */
import { apiFetch } from '@/lib/api/client'
import type { LoginRequest, RefreshTokenRequest, TokenResponse, UserResponse } from '@/lib/api/types'

export function login(payload: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/login', { method: 'POST', body: payload, auth: false })
}

export function refresh(payload: RefreshTokenRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/refresh', { method: 'POST', body: payload, auth: false })
}

export function logout(payload: RefreshTokenRequest): Promise<void> {
  return apiFetch<void>('/api/v1/auth/logout', { method: 'POST', body: payload, auth: false })
}

/** Uses the access token, unlike the three above — this is the authenticated identity check. */
export function me(signal?: AbortSignal): Promise<UserResponse> {
  return apiFetch<UserResponse>('/api/v1/auth/me', { signal })
}
