import { zodResolver } from '@hookform/resolvers/zod'
import { Clock, Mail } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import {
  createOrganizationSchema,
  type CreateOrganizationFormValues,
} from '@/features/onboarding/onboardingSchema'
import { useCreateTenant } from '@/features/onboarding/useCreateTenant'
import { useResendVerification } from '@/features/onboarding/useResendVerification'
import { isApiError } from '@/lib/api/errors'
import { describeError } from '@/lib/errors/describeError'

export function CreateOrganizationForm() {
  const createTenant = useCreateTenant()
  const resendVerification = useResendVerification()
  const [submitError, setSubmitError] = useState<unknown>(null)
  const [created, setCreated] = useState<{ slug: string; email: string } | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<CreateOrganizationFormValues>({ resolver: zodResolver(createOrganizationSchema) })

  async function onSubmit(values: CreateOrganizationFormValues) {
    setSubmitError(null)
    try {
      const result = await createTenant.mutateAsync(values)
      setCreated({ slug: result.organization_slug, email: values.adminEmail })
    } catch (error) {
      if (isApiError(error) && error.kind === 'conflict') {
        setError('organizationSlug', { message: error.message })
        return
      }
      if (isApiError(error) && error.kind === 'validation' && error.validationErrors) {
        for (const issue of error.validationErrors) {
          const field = issue.loc.at(-1)
          if (field === 'organization_slug') setError('organizationSlug', { message: issue.msg })
          else if (field === 'organization_name') setError('organizationName', { message: issue.msg })
          else if (field === 'admin_name') setError('adminName', { message: issue.msg })
          else if (field === 'admin_email') setError('adminEmail', { message: issue.msg })
          else if (field === 'admin_password') setError('adminPassword', { message: issue.msg })
        }
        return
      }
      setSubmitError(error)
    }
  }

  if (created) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <span className="flex size-14 items-center justify-center rounded-full bg-accent-50">
          <Mail className="size-6 text-accent-600" aria-hidden="true" />
        </span>

        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold text-foreground">
            Check your email
          </h2>
          <p className="mt-1.5 text-sm text-foreground-muted">
            We sent a verification link to <span className="font-medium text-foreground">{created.email}</span>.
            Follow it to activate <code>{created.slug}</code> and sign in.
          </p>
        </div>

        <div className="flex w-full items-start gap-2.5 rounded-lg border border-border bg-surface-sunken p-3 text-left">
          <Clock className="mt-0.5 size-4 shrink-0 text-foreground-muted" aria-hidden="true" />
          <p className="text-xs text-foreground-muted">
            The link works once. <code>{created.slug}</code> won't be usable — and no one can sign in — until it's
            confirmed.
          </p>
        </div>

        {resendVerification.isSuccess ? (
          <p className="text-sm text-foreground-muted">New link sent — check your inbox again.</p>
        ) : (
          <Button
            variant="secondary"
            className="w-full"
            isLoading={resendVerification.isPending}
            onClick={() =>
              resendVerification.mutate({
                organization_slug: created.slug,
                admin_email: created.email,
              })
            }
          >
            {resendVerification.isPending ? 'Sending…' : 'Resend verification email'}
          </Button>
        )}
        {resendVerification.isError && (
          <p className="text-sm text-danger-600">{describeError(resendVerification.error).message}</p>
        )}
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {submitError !== null && <Alert variant="danger">{describeError(submitError).message}</Alert>}

      <Input
        label="Organization name"
        placeholder="Acme Technologies"
        error={errors.organizationName?.message}
        {...register('organizationName')}
      />
      <Input
        label="Organization ID"
        placeholder="acme"
        error={errors.organizationSlug?.message}
        {...register('organizationSlug')}
      />
      <p className="-mt-2 text-xs text-foreground-muted">
        This is what everyone at your organization will type to sign in — choose something short and
        memorable. It can't be changed later.
      </p>

      <div className="border-t border-border" />

      <Input
        label="Your name"
        autoComplete="name"
        placeholder="Ada Lovelace"
        error={errors.adminName?.message}
        {...register('adminName')}
      />
      <Input
        label="Your email"
        type="email"
        autoComplete="email"
        error={errors.adminEmail?.message}
        {...register('adminEmail')}
      />
      <Input
        label="Password"
        type="password"
        autoComplete="new-password"
        error={errors.adminPassword?.message}
        {...register('adminPassword')}
      />

      <Button type="submit" size="lg" isLoading={createTenant.isPending} className="mt-2">
        {createTenant.isPending ? 'Creating…' : 'Create organization'}
      </Button>
    </form>
  )
}
