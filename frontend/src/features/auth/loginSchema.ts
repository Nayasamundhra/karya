import { z } from 'zod'

import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, SLUG_MAX_LENGTH } from '@/lib/validation/constants'

export const loginSchema = z.object({
  tenantSlug: z.string().trim().min(1, 'Enter your organization ID').max(SLUG_MAX_LENGTH),
  email: z.string().trim().min(1, 'Enter your email').email('Enter a valid email address'),
  password: z
    .string()
    .min(PASSWORD_MIN_LENGTH, `Password must be at least ${PASSWORD_MIN_LENGTH} characters`)
    .max(PASSWORD_MAX_LENGTH),
})

export type LoginFormValues = z.infer<typeof loginSchema>
