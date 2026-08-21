import { z } from 'zod'

// TENANT_NAME_MAX_LENGTH matches NAME_MAX_LENGTH (255) on the backend —
// see app/schemas/fields.py.
import { NAME_MAX_LENGTH } from '@/lib/validation/constants'

export const tenantSchema = z.object({
  name: z.string().trim().min(1, 'Organization name is required').max(NAME_MAX_LENGTH),
})

export type TenantFormValues = z.infer<typeof tenantSchema>
