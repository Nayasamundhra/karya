import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useLocation, useNavigate } from 'react-router-dom'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAuth } from '@/features/auth/useAuth'
import { loginSchema, type LoginFormValues } from '@/features/auth/loginSchema'
import { isApiError } from '@/lib/api/errors'
import { describeError } from '@/lib/errors/describeError'

interface LocationState {
  from?: { pathname: string }
}

/**
 * `describeError`'s generic 401 copy ("Your session has expired") is right
 * for an authenticated screen whose token died — it is the wrong sentence
 * for a login attempt that never had a session to expire. The backend's own
 * message for this endpoint ("Invalid credentials") is already the safe,
 * deliberately generic text the anti-enumeration design in backend §8a
 * requires, so this shows it verbatim rather than routing through the
 * app-wide mapping.
 */
function loginErrorMessage(error: unknown): string {
  if (isApiError(error) && error.kind === 'unauthorized') return error.message
  return describeError(error).message
}

export function LoginForm() {
  const { login, isLoggingIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [submitError, setSubmitError] = useState<unknown>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  async function onSubmit(values: LoginFormValues) {
    setSubmitError(null)
    try {
      await login({ tenantSlug: values.tenantSlug, email: values.email, password: values.password })
      const redirectTo = (location.state as LocationState | null)?.from?.pathname ?? '/'
      navigate(redirectTo, { replace: true })
    } catch (error) {
      // 422 field errors map back onto the form; everything else (401, 429,
      // network, 5xx) is a form-level alert, not attributed to one field —
      // Karya's generic "Invalid credentials" 401 must not be turned into a
      // hint about which field was wrong (that would reopen the
      // enumeration protection the backend deliberately closed).
      if (isApiError(error) && error.kind === 'validation' && error.validationErrors) {
        for (const issue of error.validationErrors) {
          const field = issue.loc.at(-1)
          if (field === 'tenant_slug') setError('tenantSlug', { message: issue.msg })
          else if (field === 'email') setError('email', { message: issue.msg })
          else if (field === 'password') setError('password', { message: issue.msg })
        }
        return
      }
      setSubmitError(error)
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {submitError !== null && <Alert variant="danger">{loginErrorMessage(submitError)}</Alert>}

      <Input
        label="Organization ID"
        autoComplete="organization"
        placeholder="acme"
        error={errors.tenantSlug?.message}
        {...register('tenantSlug')}
      />
      <Input label="Email" type="email" autoComplete="email" error={errors.email?.message} {...register('email')} />
      <Input
        label="Password"
        type="password"
        autoComplete="current-password"
        error={errors.password?.message}
        {...register('password')}
      />

      <Button type="submit" isLoading={isLoggingIn} className="mt-2">
        {isLoggingIn ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  )
}
