import { z } from 'zod'

import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from '@/lib/validation/constants'

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, 'Enter your current password'),
    newPassword: z
      .string()
      .min(PASSWORD_MIN_LENGTH, `Password must be at least ${PASSWORD_MIN_LENGTH} characters`)
      .max(PASSWORD_MAX_LENGTH),
    confirmPassword: z.string().min(1, 'Confirm your new password'),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    message: "Passwords don't match",
    path: ['confirmPassword'],
  })

export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>
