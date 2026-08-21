import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { changePasswordSchema, type ChangePasswordFormValues } from '@/features/auth/changePasswordSchema'
import { useChangePassword } from '@/features/users/useChangePassword'
import { isApiError } from '@/lib/api/errors'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export function ChangePasswordForm() {
  const changePassword = useChangePassword()
  const navigate = useNavigate()
  const [submitError, setSubmitError] = useState<unknown>(null)

  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<ChangePasswordFormValues>({ resolver: zodResolver(changePasswordSchema) })

  async function onSubmit(values: ChangePasswordFormValues) {
    setSubmitError(null)
    try {
      await changePassword.mutateAsync({
        current_password: values.currentPassword,
        new_password: values.newPassword,
      })
      reset()
      toast.success('Password changed', 'Sign in again with your new password.')
      navigate('/login', { replace: true })
    } catch (error) {
      // A wrong current password is a generic 401 (see backend §8e) —
      // attributed to the field so the person knows what to fix, but the
      // message itself stays the backend's generic one rather than
      // confirming "current password" specifically was wrong (the backend
      // already made this decision; the frontend just places the message).
      if (isApiError(error) && error.kind === 'unauthorized') {
        setError('currentPassword', { message: 'Incorrect password' })
        return
      }
      if (isApiError(error) && error.kind === 'validation' && error.validationErrors) {
        for (const issue of error.validationErrors) {
          if (issue.loc.at(-1) === 'new_password') setError('newPassword', { message: issue.msg })
        }
        return
      }
      // 400 (PasswordUnchangedError / PasswordTooSimilarError) — the backend's
      // message is already safe, specific, user-facing text (see users.py).
      if (isApiError(error) && error.status === 400) {
        setError('newPassword', { message: error.message })
        return
      }
      setSubmitError(error)
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {submitError !== null && <Alert variant="danger">{describeError(submitError).message}</Alert>}
      <Input
        label="Current password"
        type="password"
        autoComplete="current-password"
        error={errors.currentPassword?.message}
        {...register('currentPassword')}
      />
      <Input
        label="New password"
        type="password"
        autoComplete="new-password"
        error={errors.newPassword?.message}
        {...register('newPassword')}
      />
      <Input
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        error={errors.confirmPassword?.message}
        {...register('confirmPassword')}
      />
      <Alert variant="warning">Changing your password signs out every other device.</Alert>
      <div>
        <Button type="submit" isLoading={changePassword.isPending}>
          {changePassword.isPending ? 'Changing password…' : 'Change password'}
        </Button>
      </div>
    </form>
  )
}
