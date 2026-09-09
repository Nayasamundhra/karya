import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as onboardingApi from '@/lib/api/endpoints/onboarding'
import { establishSessionFromTokens } from '@/lib/auth/session'

export function useVerifyEmail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) => onboardingApi.verifyEmail({ token }),
    onSuccess: async (tokens) => {
      // Nothing about this admin's tenant/profile could have been cached
      // under a previous session on this device — but establishing a brand
      // new session is exactly the case `queryClient.clear()` exists for
      // elsewhere (see `useAuth`'s logout), so the same discipline applies.
      queryClient.clear()
      await establishSessionFromTokens(tokens)
    },
  })
}
