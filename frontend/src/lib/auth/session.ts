/**
 * Session orchestration: login, logout, silent refresh, and the one-time
 * bootstrap that runs when the app loads. This is the module that wires
 * `authStore` (in-memory session state) to `tokenStorage` (the persisted
 * refresh token) to `client.ts` (which needs both, without importing either
 * directly — see `configureApiAuth`).
 *
 * Nothing here is React. `src/features/auth/useAuth.ts` is the hook layer
 * components actually use; this module is what that hook calls into.
 */
import * as authApi from '@/lib/api/endpoints/auth'
import { configureApiAuth } from '@/lib/api/client'
import { isApiError } from '@/lib/api/errors'
import { clearRefreshToken, loadRefreshToken, saveRefreshToken } from '@/lib/auth/tokenStorage'
import { useAuthStore } from '@/stores/authStore'

// Listeners for "the session just ended" (logout, expiry, or a rejected
// refresh) that need to react outside the store itself — chiefly, clearing
// TanStack Query's cache so the next person to sign in on a shared device
// never sees a flash of the previous user's cached data. Registered once by
// `src/app/providers.tsx`; deliberately a plain callback list rather than an
// event target, since there is exactly one real subscriber.
const sessionClearedListeners = new Set<() => void>()

export function onSessionCleared(listener: () => void): () => void {
  sessionClearedListeners.add(listener)
  return () => sessionClearedListeners.delete(listener)
}

function endSession(): void {
  clearRefreshToken()
  useAuthStore.getState().clearSession()
  for (const listener of sessionClearedListeners) listener()
}

async function performRefresh(): Promise<string> {
  const refreshToken = loadRefreshToken()
  if (!refreshToken) throw new Error('No refresh token available')

  const tokens = await authApi.refresh({ refresh_token: refreshToken })
  // Rotation (Phase 2): the old refresh token is now revoked server-side, so
  // the new one MUST replace it immediately — there is no window in which
  // holding onto the old value would help.
  saveRefreshToken(tokens.refresh_token)

  const currentUser = useAuthStore.getState().user
  if (currentUser) {
    useAuthStore
      .getState()
      .setSession({ user: currentUser, accessToken: tokens.access_token, expiresInSeconds: tokens.expires_in })
  }
  return tokens.access_token
}

// Wired once, at module load — `client.ts` never imports this module, only
// exposes the seam this call fills in. See that module's header comment.
configureApiAuth({
  getAccessToken: () => useAuthStore.getState().accessToken,
  refreshAccessToken: performRefresh,
  onSessionExpired: endSession,
})

/**
 * Run once when the app boots. If a refresh token survived from a previous
 * visit, exchange it for a fresh access token and load the profile; if not
 * — or if the exchange fails for any reason (expired, revoked, deactivated
 * account) — the session ends up `unauthenticated` with no error surfaced,
 * because "you're not signed in yet" is not a failure.
 */
export async function bootstrapSession(): Promise<void> {
  const refreshToken = loadRefreshToken()
  if (!refreshToken) {
    useAuthStore.getState().clearSession()
    return
  }

  try {
    const tokens = await authApi.refresh({ refresh_token: refreshToken })
    saveRefreshToken(tokens.refresh_token)
    const user = await authApi.me()
    useAuthStore.getState().setSession({
      user,
      accessToken: tokens.access_token,
      expiresInSeconds: tokens.expires_in,
    })
  } catch {
    endSession()
  }
}

export interface LoginParams {
  tenantSlug: string
  email: string
  password: string
}

/** Throws `ApiError` on failure — the caller (the login form) renders it. */
export async function login(params: LoginParams): Promise<void> {
  const tokens = await authApi.login({
    tenant_slug: params.tenantSlug,
    email: params.email,
    password: params.password,
  })
  saveRefreshToken(tokens.refresh_token)
  const user = await authApi.me()
  useAuthStore.getState().setSession({
    user,
    accessToken: tokens.access_token,
    expiresInSeconds: tokens.expires_in,
  })
}

/**
 * Revoke the current refresh session and clear local state. The backend
 * call is best-effort: if it fails (already logged out elsewhere, offline,
 * server error) the local session ends anyway — a user who clicked "log
 * out" must never be left looking signed in.
 */
export async function logout(): Promise<void> {
  const refreshToken = loadRefreshToken()
  try {
    if (refreshToken) await authApi.logout({ refresh_token: refreshToken })
  } catch (error) {
    if (!isApiError(error)) throw error
    // Swallow — see docstring. A network/5xx/429 on logout is not something
    // the user can act on, and the local session is about to end regardless.
  } finally {
    endSession()
  }
}
