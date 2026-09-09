import { zodResolver } from '@hookform/resolvers/zod'
import { AlertTriangle, MailQuestion } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { FullScreenSpinner } from '@/components/layout/FullScreenSpinner'
import {
  resendVerificationSchema,
  type ResendVerificationFormValues,
} from '@/features/onboarding/onboardingSchema'
import { useResendVerification } from '@/features/onboarding/useResendVerification'
import { useVerifyEmail } from '@/features/onboarding/useVerifyEmail'
import { isApiError } from '@/lib/api/errors'
import { describeError } from '@/lib/errors/describeError'

/**
 * `describeError`'s generic 401 copy ("Your session has expired, sign in
 * again") is right for an authenticated screen whose token died — it is the
 * wrong sentence for a one-time verification link that never was a session.
 * The backend's own message here ("This verification link is invalid or has
 * expired") is already the deliberately generic, anti-enumeration-safe text
 * (see backend `onboarding.py`), so this shows it verbatim — the same
 * exception `LoginForm.tsx` makes for its own non-session 401.
 */
function verificationErrorMessage(error: unknown): string {
  if (isApiError(error) && error.kind === 'unauthorized') return error.message
  return describeError(error).message
}

/**
 * Landing page for the link emailed by `POST /onboarding/tenants`. Fires the
 * verification exactly once per mount (the `hasRun` guard), since this
 * token is single-use server-side — a second attempt (e.g. React re-running
 * an effect in dev, or the user hitting refresh) must not be mistaken for
 * a real retry-worthy failure.
 *
 * Deliberately tracks outcome in local state (`verificationError`) rather
 * than reading `verifyEmail.isSuccess`/`isError` - React 19 StrictMode's
 * dev-only mount→cleanup→remount simulation can detach `useMutation`'s
 * reactive state (and any callback passed to `.mutate()`) from a mutation
 * that was *started* during that simulated first mount, even though the
 * mutation itself completes normally: `mutationFn` runs, the hook's own
 * `onSuccess` runs (so the session really is established), but nothing
 * ever tells this component - the page is left showing its spinner forever
 * (confirmed: reproduces every time in `npm run dev`, never in a
 * production build, and never for a `.mutate()` triggered later by a user
 * action, e.g. `ResendVerificationForm` below - only one fired from an
 * effect at mount races the StrictMode simulation). `mutateAsync()`'s
 * returned promise is not part of that reactive wiring, so it settles
 * reliably regardless; driving both the redirect and the error branch from
 * it sidesteps the bug entirely rather than depending on which mount wins.
 */
export default function VerifyEmailPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const verifyEmail = useVerifyEmail()
  const hasRun = useRef(false)
  const [verificationError, setVerificationError] = useState<unknown>(null)

  useEffect(() => {
    if (hasRun.current || !token) return
    hasRun.current = true
    verifyEmail.mutateAsync(token).then(
      () => navigate('/setup', { replace: true }),
      (error: unknown) => setVerificationError(error),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-sunken p-4">
        <Card className="w-full max-w-sm">
          <CardContent className="flex flex-col items-center gap-3 pt-6 text-center">
            <span className="flex size-14 items-center justify-center rounded-full bg-danger-50">
              <MailQuestion className="size-6 text-danger-600" aria-hidden="true" />
            </span>
            <div>
              <h1 className="font-[family-name:var(--font-display)] text-lg font-semibold text-foreground">
                Missing verification link
              </h1>
              <p className="mt-1.5 text-sm text-foreground-muted">
                Open this page using the link from your email — it wasn't included this time.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (verificationError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-sunken p-4">
        <Card className="w-full max-w-sm">
          <CardContent className="flex flex-col items-center gap-4 pt-6 text-center">
            <span className="flex size-14 items-center justify-center rounded-full bg-warning-50">
              <AlertTriangle className="size-6 text-warning-600" aria-hidden="true" />
            </span>
            <div>
              <h1 className="font-[family-name:var(--font-display)] text-lg font-semibold text-foreground">
                Verification failed
              </h1>
              <p className="mt-1.5 text-sm text-foreground-muted">{verificationErrorMessage(verificationError)}</p>
            </div>
            <ResendVerificationForm />
            <Button variant="ghost" className="w-full" onClick={() => navigate('/onboarding')}>
              Create a new organization
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return <FullScreenSpinner label="Verifying your account…" />
}

/**
 * Unlike `CreateOrganizationForm`'s resend button, this page only ever has a
 * dead token — never the organization/email that link belonged to — so
 * recovering means asking for both again, the same two things login does.
 */
function ResendVerificationForm() {
  const resendVerification = useResendVerification()
  const [sent, setSent] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResendVerificationFormValues>({ resolver: zodResolver(resendVerificationSchema) })

  if (sent) {
    return (
      <p className="text-sm text-foreground-muted">
        If that account needs verifying, a new link is on its way — check your inbox.
      </p>
    )
  }

  return (
    <form
      onSubmit={handleSubmit((values) => {
        resendVerification.mutate(
          { organization_slug: values.organizationSlug, admin_email: values.adminEmail },
          { onSuccess: () => setSent(true) },
        )
      })}
      className="flex w-full flex-col gap-3 text-left"
      noValidate
    >
      <p className="text-sm text-foreground-muted">Get a fresh link sent to you:</p>
      <Input
        label="Organization ID"
        placeholder="acme"
        error={errors.organizationSlug?.message}
        {...register('organizationSlug')}
      />
      <Input
        label="Your email"
        type="email"
        autoComplete="email"
        error={errors.adminEmail?.message}
        {...register('adminEmail')}
      />
      {resendVerification.isError && (
        <p className="text-sm text-danger-600">{describeError(resendVerification.error).message}</p>
      )}
      <Button type="submit" variant="secondary" isLoading={resendVerification.isPending}>
        {resendVerification.isPending ? 'Sending…' : 'Resend verification email'}
      </Button>
    </form>
  )
}
