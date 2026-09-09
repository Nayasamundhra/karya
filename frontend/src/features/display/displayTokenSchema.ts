import { z } from 'zod'

export const createDisplayTokenSchema = z.object({
  label: z.string().trim().min(1, 'Give this display a name').max(255),
})

export type CreateDisplayTokenFormValues = z.infer<typeof createDisplayTokenSchema>
