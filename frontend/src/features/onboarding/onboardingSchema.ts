import { z } from 'zod'

import {
  NAME_MAX_LENGTH,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  SLUG_MAX_LENGTH,
  TENANT_NAME_MAX_LENGTH,
  TENANT_SLUG_PATTERN,
} from '@/lib/validation/constants'

export const createOrganizationSchema = z.object({
  organizationName: z.string().trim().min(1, 'Organization name is required').max(TENANT_NAME_MAX_LENGTH),
  organizationSlug: z
    .string()
    .trim()
    .toLowerCase()
    .min(1, 'Choose an organization ID')
    .max(SLUG_MAX_LENGTH)
    .regex(
      TENANT_SLUG_PATTERN,
      'Lowercase letters, numbers and hyphens only — must start and end with a letter or number',
    ),
  adminName: z.string().trim().min(1, 'Your name is required').max(NAME_MAX_LENGTH),
  adminEmail: z.string().trim().min(1, 'Enter your email').email('Enter a valid email address'),
  adminPassword: z
    .string()
    .min(PASSWORD_MIN_LENGTH, `Password must be at least ${PASSWORD_MIN_LENGTH} characters`)
    .max(PASSWORD_MAX_LENGTH),
})

export type CreateOrganizationFormValues = z.infer<typeof createOrganizationSchema>

/** `VerifyEmailPage`'s recovery form — it only knows a dead token, not the
 * account, so it asks for the same two things login does. */
export const resendVerificationSchema = z.object({
  organizationSlug: z
    .string()
    .trim()
    .toLowerCase()
    .min(1, 'Enter your organization ID')
    .max(SLUG_MAX_LENGTH)
    .regex(TENANT_SLUG_PATTERN, 'Lowercase letters, numbers and hyphens only'),
  adminEmail: z.string().trim().min(1, 'Enter your email').email('Enter a valid email address'),
})

export type ResendVerificationFormValues = z.infer<typeof resendVerificationSchema>
