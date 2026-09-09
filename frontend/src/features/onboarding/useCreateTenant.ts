import { useMutation } from '@tanstack/react-query'

import * as onboardingApi from '@/lib/api/endpoints/onboarding'
import type { CreateOrganizationFormValues } from '@/features/onboarding/onboardingSchema'

export function useCreateTenant() {
  return useMutation({
    mutationFn: (values: CreateOrganizationFormValues) =>
      onboardingApi.createTenant({
        organization_name: values.organizationName,
        organization_slug: values.organizationSlug,
        admin_name: values.adminName,
        admin_email: values.adminEmail,
        admin_password: values.adminPassword,
      }),
  })
}
