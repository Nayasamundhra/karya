import { z } from 'zod'

import { NAME_MAX_LENGTH } from '@/lib/validation/constants'

export const profileSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(NAME_MAX_LENGTH),
})

export type ProfileFormValues = z.infer<typeof profileSchema>
