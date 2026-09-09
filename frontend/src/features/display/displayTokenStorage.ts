/**
 * Persistence for the kiosk's own display token — see `KioskPage`.
 *
 * `localStorage`, not `sessionStorage`, for the same reason
 * `lib/auth/tokenStorage.ts` uses it for the refresh token: a kiosk display
 * is meant to stay set up indefinitely across reloads and power cycles, not
 * re-prompt for its token every time the tab reopens. Unlike a refresh
 * token, a display token is never rotated and grants exactly one narrow
 * capability (see `app.api.display_deps`), so the exposure this accepts is
 * already small; it is still never mixed into `authStore` or sent as a
 * normal user's bearer token (`client.ts`'s `token` override keeps the two
 * paths separate).
 */

const DISPLAY_TOKEN_KEY = 'karya.display_token'

function storageAvailable(): boolean {
  try {
    const probe = '__karya_probe__'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
    return true
  } catch {
    return false
  }
}

export function loadDisplayToken(): string | null {
  if (!storageAvailable()) return null
  return window.localStorage.getItem(DISPLAY_TOKEN_KEY)
}

export function saveDisplayToken(token: string): void {
  if (!storageAvailable()) return
  window.localStorage.setItem(DISPLAY_TOKEN_KEY, token)
}

export function clearDisplayToken(): void {
  if (!storageAvailable()) return
  window.localStorage.removeItem(DISPLAY_TOKEN_KEY)
}
