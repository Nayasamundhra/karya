/**
 * Light/dark theme preference.
 *
 * Light is the default for everyone, always — the app deliberately does NOT
 * follow the OS `prefers-color-scheme`. Following it meant the public pages
 * (landing / login / sign up, which are fixed light) and the signed-in app
 * could disagree on the same machine, so a user who signed up in light mode
 * landed in a dark dashboard without having chosen it. Dark is now strictly
 * opt-in via the toggle in the user menu, and the choice is remembered.
 *
 * Not a Zustand store on purpose: the app keeps exactly two (auth, toasts),
 * and this is one string in `localStorage` plus an attribute on <html> —
 * `useSyncExternalStore` (see `hooks/useTheme.ts`) is all it needs.
 *
 * `index.html` runs an inline copy of `readStoredTheme` before first paint so
 * a returning dark-mode user never sees a flash of light; keep the two in
 * step (same key, same `'dark'`-or-nothing rule).
 */
export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'karya-theme'

const THEME_COLOR: Record<Theme, string> = { light: '#faf9f6', dark: '#0a0a0b' }

const listeners = new Set<() => void>()

/** Anything other than an explicit stored `'dark'` is light — including a
 * missing key, a corrupt value, and storage being unavailable. */
export function readStoredTheme(): Theme {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/** The theme currently applied to the document (what the user actually sees). */
export function getAppliedTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme])
  listeners.forEach((listener) => listener())
}

export function setTheme(theme: Theme): void {
  try {
    if (theme === 'dark') localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    else localStorage.removeItem(THEME_STORAGE_KEY)
  } catch {
    // Private mode / blocked storage: the choice still applies for this
    // session, it just won't be remembered.
  }
  applyTheme(theme)
}

export function subscribeToTheme(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
