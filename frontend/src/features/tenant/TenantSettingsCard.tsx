import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/feedback/ErrorState'
import { useTenant } from '@/features/tenant/useTenant'
import { useUpdateTenant } from '@/features/tenant/useUpdateTenant'
import { tenantSchema, type TenantFormValues } from '@/features/tenant/tenantSchema'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export function TenantSettingsCard() {
  const { data: tenant, isLoading, isError, error, refetch } = useTenant()
  const updateTenant = useUpdateTenant()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<TenantFormValues>({ resolver: zodResolver(tenantSchema), defaultValues: { name: tenant?.name ?? '' } })

  useEffect(() => {
    if (tenant && !isDirty) reset({ name: tenant.name })
  }, [tenant, isDirty, reset])

  async function onSubmit(values: TenantFormValues) {
    try {
      await updateTenant.mutateAsync({ name: values.name })
      toast.success('Organization updated')
    } catch (err) {
      toast.error('Could not update organization', describeError(err).message)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organization</CardTitle>
        <CardDescription>
          Only the display name can be changed here. The organization ID (
          <code>{tenant?.slug}</code>) is what everyone uses to sign in, so it can't be changed
          from this screen.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-11 w-full" />}
        {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
        {tenant && (
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
            <Input label="Organization name" error={errors.name?.message} {...register('name')} />
            <div>
              <Button type="submit" isLoading={updateTenant.isPending} disabled={!isDirty}>
                {updateTenant.isPending ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
