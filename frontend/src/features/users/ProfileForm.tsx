import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { profileSchema, type ProfileFormValues } from '@/features/users/profileSchema'
import { useUpdateOwnProfile } from '@/features/users/useOwnProfile'
import { describeError } from '@/lib/errors/describeError'
import type { UserResponse } from '@/lib/api/types'
import { toast } from '@/stores/toastStore'

export function ProfileForm({ user }: { user: UserResponse }) {
  const updateProfile = useUpdateOwnProfile()
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProfileFormValues>({ resolver: zodResolver(profileSchema), defaultValues: { name: user.name } })

  // Keep the form in sync if the profile is refetched with a different name
  // (e.g. changed by an administrator) — but only while the user hasn't
  // started typing an edit of their own, so we never clobber unsaved input.
  useEffect(() => {
    if (!isDirty) reset({ name: user.name })
  }, [user.name, isDirty, reset])

  async function onSubmit(values: ProfileFormValues) {
    try {
      await updateProfile.mutateAsync({ name: values.name })
      toast.success('Profile updated')
    } catch (error) {
      toast.error('Could not update profile', describeError(error).message)
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <Input label="Name" error={errors.name?.message} {...register('name')} />
      <Input label="Email" value={user.email} disabled hint="Contact your administrator to change your email." />
      <Input label="Employee code" value={user.employee_code} disabled />
      <div>
        <Button type="submit" isLoading={updateProfile.isPending} disabled={!isDirty}>
          {updateProfile.isPending ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </form>
  )
}
