import { z } from 'zod'

import { EMPLOYEE_CODE_MAX_LENGTH, NAME_MAX_LENGTH, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from '@/lib/validation/constants'
import { ASSIGNABLE_ROLES } from '@/lib/api/types'

export const createEmployeeSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(NAME_MAX_LENGTH),
  email: z.string().trim().min(1, 'Enter an email').email('Enter a valid email address'),
  employee_code: z.string().trim().min(1, 'Employee code is required').max(EMPLOYEE_CODE_MAX_LENGTH),
  // SUPER_ADMIN is a platform role the backend itself rejects here (422), so
  // it's never offered as a choice — `ASSIGNABLE_ROLES` is the one place
  // that list is defined (also used for the role-change dialog and the
  // create-employee <Select>).
  role: z.enum(ASSIGNABLE_ROLES),
  password: z
    .string()
    .min(PASSWORD_MIN_LENGTH, `Password must be at least ${PASSWORD_MIN_LENGTH} characters`)
    .max(PASSWORD_MAX_LENGTH),
})
export type CreateEmployeeFormValues = z.infer<typeof createEmployeeSchema>

export const editEmployeeSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(NAME_MAX_LENGTH),
  email: z.string().trim().min(1, 'Enter an email').email('Enter a valid email address'),
  employee_code: z.string().trim().min(1, 'Employee code is required').max(EMPLOYEE_CODE_MAX_LENGTH),
})
export type EditEmployeeFormValues = z.infer<typeof editEmployeeSchema>
