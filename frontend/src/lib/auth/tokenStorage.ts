/**
 * Refresh-token persistence — the one deliberate exception to "never persist
 * a token", and worth reading `docs/auth.md` before touching.
 *
 * Karya's backend (Phase 2) returns the refresh token as a JSON body field on
 * `/auth/login` and `/auth/refresh`, not as an HttpOnly cookie set by the
 * server. That is the existing, verified backend contract, and this phase
 * does not change it (see CLAUDE.md — no backend changes without a clearly
 * justified frontend integration issue). Given that contract, there is no
 * way for the frontend to hold a 30-day session across a page reload without
 * *some* client-side persistence, because nothing else survives a reload.
 *
 * The access token never goes here — it lives only in `authStore`'s
 * in-memory state (see that module), which a fresh page load simply does not
 * have. Only the refresh token is written to `localStorage`, which bounds
 * what a successful XSS could steal to "a token that must still be actively
 * exchanged, and whose use rotates it" rather than a permanently valid bearer
 * credential.
 *
 * `sessionStorage` was considered and rejected: it clears on tab close, which
 * would force a fresh login every time a PWA is relaunched from a home-screen
 * icon — exactly the "stays signed in" behaviour a mobile attendance app
 * needs. `localStorage` is the only web storage that survives that.
 */

const REFRESH_TOKEN_KEY = 'karya.refresh_token'

function storageAvailable(): boolean {
  try {
    const probe = '__karya_probe__'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
    return true
  } catch {
    // Safari private mode, disabled storage, or a storage quota error.
    return false
  }
}

export function loadRefreshToken(): string | null {
  if (!storageAvailable()) return null
  return window.localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function saveRefreshToken(token: string): void {
  if (!storageAvailable()) return
  window.localStorage.setItem(REFRESH_TOKEN_KEY, token)
}

export function clearRefreshToken(): void {
  if (!storageAvailable()) return
  window.localStorage.removeItem(REFRESH_TOKEN_KEY)
}
