import { useMutation } from '@tanstack/react-query'

import * as usersApi from '@/lib/api/endpoints/users'
import type { PasswordChangeRequest } from '@/lib/api/types'
import { logout } from '@/lib/auth/session'

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: PasswordChangeRequest) => usersApi.changeOwnPassword(payload),
    onSuccess: async () => {
      // The backend revokes every refresh session on a successful change
      // (see backend README §8e) — including the one this tab is using.
      // Signing this tab out too, rather than leaving it holding a
      // soon-to-be-useless access token, keeps the client's idea of "am I
      // signed in" honest.
      await logout()
    },
  })
}
