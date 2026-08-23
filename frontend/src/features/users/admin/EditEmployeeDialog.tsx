/**
 * Editing an employee's profile fields (§12) — `email`, `name`,
 * `employee_code` only, matching the backend's `UserUpdateRequest` exactly.
 * Role and status are never editable here; those have their own dedicated
 * actions (`ChangeRoleDialog`, activate/deactivate) because the backend
 * exposes them as separate endpoints with their own safety checks.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'

import { Button } from '@/components/ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { editEmployeeSchema, type EditEmployeeFormValues } from '@/features/users/admin/userSchemas'
import { useUpdateEmployee } from '@/features/users/admin/useUserMutations'
import { isApiError } from '@/lib/api/errors'
import type { UserDetailResponse } from '@/lib/api/types'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export interface EditEmployeeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employee: UserDetailResponse
}

export function EditEmployeeDialog({ open, onOpenChange, employee }: EditEmployeeDialogProps) {
  const updateEmployee = useUpdateEmployee()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<EditEmployeeFormValues>({
    resolver: zodResolver(editEmployeeSchema),
    defaultValues: { name: employee.name, email: employee.email, employee_code: employee.employee_code },
  })

  // Reset to the current row's values whenever a different employee is
  // opened for editing (the dialog instance is shared across rows).
  useEffect(() => {
    if (open) reset({ name: employee.name, email: employee.email, employee_code: employee.employee_code })
  }, [open, employee, reset])

  async function onSubmit(values: EditEmployeeFormValues) {
    try {
      await updateEmployee.mutateAsync({ userId: employee.id, payload: values })
      toast.success('Employee updated')
      onOpenChange(false)
    } catch (error) {
      if (isApiError(error) && error.kind === 'conflict') {
        if (error.message.toLowerCase().includes('employee code')) {
          setError('employee_code', { message: error.message })
        } else {
          setError('email', { message: error.message })
        }
        return
      }
      toast.error('Could not update employee', describeError(error).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !updateEmployee.isPending && onOpenChange(next)}>
      <DialogContent onEscapeKeyDown={(e) => updateEmployee.isPending && e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Edit employee</DialogTitle>
          <DialogDescription>Update {employee.name}'s profile details.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <Input label="Name" error={errors.name?.message} {...register('name')} />
          <Input label="Email" type="email" error={errors.email?.message} {...register('email')} />
          <Input label="Employee code" error={errors.employee_code?.message} {...register('employee_code')} />
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={updateEmployee.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" isLoading={updateEmployee.isPending}>
              {updateEmployee.isPending ? 'Saving…' : 'Save changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
