/**
 * Global session state. This is the one Zustand store in the app that holds
 * genuinely global client state — every route, the shell, the API client and
 * every feature needs to know "who is signed in and are we sure yet", and
 * none of that is server data TanStack Query should own (the *fact* of being
 * signed in isn't a cacheable resource — `/auth/me`, the actual profile
 * data, is, and is fetched through TanStack Query in `useAuth`, not stored
 * here).
 *
 * Deliberately excluded from this store: the refresh token (see
 * `lib/auth/tokenStorage.ts` — kept out of any state a devtools extension or
 * error-reporting snapshot might serialize) and no `persist` middleware is
 * used — the access token must NOT survive a reload; only `bootstrapSession`
 * (in `lib/auth/session.ts`) is allowed to repopulate this store, and only
 * via a fresh `/auth/refresh` + `/auth/me` round trip.
 */
import { create } from 'zustand'

import type { UserResponse } from '@/lib/api/types'

export type SessionStatus =
  /** Bootstrapping: checking for a persisted refresh token on app start. */
  | 'loading'
  | 'authenticated'
  | 'unauthenticated'

interface AuthState {
  status: SessionStatus
  user: UserResponse | null
  accessToken: string | null
  accessTokenExpiresAt: number | null
  setSession: (params: { user: UserResponse; accessToken: string; expiresInSeconds: number }) => void
  setUser: (user: UserResponse) => void
  clearSession: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'loading',
  user: null,
  accessToken: null,
  accessTokenExpiresAt: null,

  setSession: ({ user, accessToken, expiresInSeconds }) =>
    set({
      status: 'authenticated',
      user,
      accessToken,
      accessTokenExpiresAt: Date.now() + expiresInSeconds * 1000,
    }),

  setUser: (user) => set({ user }),

  clearSession: () =>
    set({ status: 'unauthenticated', user: null, accessToken: null, accessTokenExpiresAt: null }),
}))

/** Non-reactive read for code outside React (the API client's auth hooks). */
export function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken
}
