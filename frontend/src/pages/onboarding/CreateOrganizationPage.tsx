import { Link } from 'react-router-dom'

import { CreateOrganizationForm } from '@/features/onboarding/CreateOrganizationForm'
import { BrandMark } from '@/features/marketing/BrandMark'
import { eyebrowClass } from '@/features/marketing/brandStyles'
import { cn } from '@/lib/utils/cn'

const STEPS = [
  'Create your organization.',
  'Verify your email.',
  'Place the office, print the QR, add employees.',
]

/**
 * The one public, unauthenticated write surface in the whole app (see the
 * backend's own `POST /onboarding/tenants` docstring) — worth a real first
 * impression rather than a generic centered card. The plum panel is
 * `hidden lg:flex`: on a phone the form is the only thing that matters.
 *
 * The three steps on the panel mirror the real flow: this form, the emailed
 * verification link (`/onboarding/verify`), then the setup checklist.
 */
export default function CreateOrganizationPage() {
  return (
    <div className="theme-brand flex min-h-screen">
      <aside className="hidden w-[480px] shrink-0 flex-col justify-between bg-brand-plum p-16 text-white lg:flex">
        <BrandMark tone="dark" className="self-start" />

        <div className="max-w-[420px]">
          <h2 className="font-brand text-[44px] font-semibold leading-[1.1] tracking-tight text-balance">
            Start with your office. Add the team after.
          </h2>
          <ol className="mt-8 flex flex-col gap-5">
            {STEPS.map((step, index) => (
              <li key={step} className="flex items-start gap-4">
                <span
                  aria-hidden="true"
                  className={cn(
                    'flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                    index === 0 ? 'bg-brand-gold text-brand-plum' : 'border border-white/40',
                  )}
                >
                  {index + 1}
                </span>
                <span className="text-base leading-normal text-white/85">{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <p className="text-[13px] text-white/65">You become the organization's admin.</p>
      </aside>

      <div className="flex min-w-0 flex-1 items-center justify-center px-6 py-10 sm:px-12 lg:px-16">
        <div className="w-full max-w-[440px]">
          <BrandMark className="mb-8 lg:hidden" />

          <span className={cn(eyebrowClass, 'block text-brand-purple-deep')}>Sign up</span>
          <h1 className="mt-3 font-brand text-4xl font-semibold leading-[1.05] tracking-tight sm:text-[44px]">
            Create your organization
          </h1>
          <p className="mt-3 text-base leading-normal text-brand-indigo/65">
            You'll be the first admin — invite your team once you're in.
          </p>

          <div className="mt-8">
            <CreateOrganizationForm />
          </div>

          <p className="mt-6 text-sm text-brand-indigo/65">
            Already have an organization on Karya?{' '}
            <Link to="/login" className="font-semibold text-brand-purple-deep hover:underline">
              Log in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
