/**
 * Employee creation (§11) — only the fields the backend's `UserCreateRequest`
 * actually accepts. Never logs or displays the password after submission;
 * the input just gets cleared when the dialog closes (`reset()` + unmount).
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'

import { Button } from '@/components/ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'
import { createEmployeeSchema, type CreateEmployeeFormValues } from '@/features/users/admin/userSchemas'
import { ROLE_LABEL } from '@/features/users/admin/roleLabels'
import { useCreateEmployee } from '@/features/users/admin/useUserMutations'
import { isApiError } from '@/lib/api/errors'
import { ASSIGNABLE_ROLES } from '@/lib/api/types'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export interface CreateEmployeeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateEmployeeDialog({ open, onOpenChange }: CreateEmployeeDialogProps) {
  const createEmployee = useCreateEmployee()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    control,
    formState: { errors },
  } = useForm<CreateEmployeeFormValues>({
    resolver: zodResolver(createEmployeeSchema),
    defaultValues: { name: '', email: '', employee_code: '', role: 'STAFF', password: '' },
  })

  async function onSubmit(values: CreateEmployeeFormValues) {
    try {
      const created = await createEmployee.mutateAsync(values)
      toast.success('Employee created', `${created.name} can now sign in.`)
      reset()
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
      toast.error('Could not create employee', describeError(error).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !createEmployee.isPending && onOpenChange(next)}>
      <DialogContent onEscapeKeyDown={(e) => createEmployee.isPending && e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Add employee</DialogTitle>
          <DialogDescription>Create an account for a new employee in your organization.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <Input label="Name" error={errors.name?.message} {...register('name')} />
          <Input label="Email" type="email" error={errors.email?.message} {...register('email')} />
          <Input label="Employee code" error={errors.employee_code?.message} {...register('employee_code')} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="create-employee-role">Role</Label>
            <Controller
              name="role"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="create-employee-role" aria-label="Role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ASSIGNABLE_ROLES.map((role) => (
                      <SelectItem key={role} value={role}>
                        {ROLE_LABEL[role]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            error={errors.password?.message}
            {...register('password')}
          />
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={createEmployee.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" isLoading={createEmployee.isPending}>
              {createEmployee.isPending ? 'Creating…' : 'Create employee'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
