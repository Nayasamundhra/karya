import { useMutation } from '@tanstack/react-query'

import * as onboardingApi from '@/lib/api/endpoints/onboarding'
import type { ResendVerificationRequest } from '@/lib/api/types'

/** Backs the "Resend verification email" action on both `CreateOrganizationForm`'s
 * post-signup state and `VerifyEmailPage`'s expired/invalid-link state. */
export function useResendVerification() {
  return useMutation({
    mutationFn: (payload: ResendVerificationRequest) => onboardingApi.resendVerification(payload),
  })
}
