import { Link } from 'react-router-dom'

import { LoginForm } from '@/features/auth/LoginForm'
import { BrandMark } from '@/features/marketing/BrandMark'
import { eyebrowClass } from '@/features/marketing/brandStyles'
import { cn } from '@/lib/utils/cn'

/**
 * The mirror image of the sign-up page (`CreateOrganizationPage`): the same
 * plum brand panel on the left, the form on the right, so moving between the
 * two reads as one flow. The panel is `hidden lg:flex` — on a phone the form is
 * the only thing that matters, and it gets its own brand mark above it.
 *
 * The "18 of 24 in" card on the panel is illustrative, not live data — this
 * page is signed-out, so there is nothing real to show.
 */
export default function LoginPage() {
  return (
    <div className="theme-brand flex min-h-screen">
      <aside className="hidden w-[480px] shrink-0 flex-col justify-between bg-brand-plum p-16 text-white lg:flex">
        <BrandMark tone="dark" className="self-start" />

        <div className="max-w-[420px]">
          <span className={cn(eyebrowClass, 'text-brand-gold')}>Welcome back</span>
          <h2 className="mt-4 font-brand text-[44px] font-semibold leading-[1.1] tracking-tight text-balance">
            Attendance you can trust.
          </h2>
          <p className="mt-5 text-[17px] text-white/75">Scan. Verify. Done.</p>
        </div>

        <div aria-hidden="true" className="max-w-[360px] rounded-3xl border border-white/15 bg-white/10 p-6">
          <div className="flex items-center justify-between">
            <span className={cn(eyebrowClass, 'text-white/75')}>Team today</span>
            <span className="text-xs font-semibold text-brand-gold">Live</span>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-[44px] font-semibold tracking-tight">18</span>
            <span className="text-[15px] text-white/75">of 24 in</span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/15">
            <div className="h-full w-3/4 rounded-full bg-brand-gold" />
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 items-center justify-center px-6 py-10 sm:px-12 lg:px-16">
        <div className="w-full max-w-[440px]">
          <BrandMark className="mb-8 lg:hidden" />

          <span className={cn(eyebrowClass, 'block text-brand-purple-deep')}>Log in</span>
          <h1 className="mt-3 font-brand text-4xl font-semibold leading-[1.05] tracking-tight sm:text-[44px]">
            Welcome back.
          </h1>
          <p className="mt-3 text-base leading-normal text-brand-indigo/65">
            Log in to your organization to check in and see your team.
          </p>

          <div className="mt-8">
            <LoginForm />
          </div>

          <p className="mt-6 text-sm text-brand-indigo/65">
            New to Karya?{' '}
            <Link to="/onboarding" className="font-semibold text-brand-purple-deep hover:underline">
              Create an organization
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
