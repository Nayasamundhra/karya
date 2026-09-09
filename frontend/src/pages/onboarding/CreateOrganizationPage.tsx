import { MapPin, MonitorSmartphone, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { CreateOrganizationForm } from '@/features/onboarding/CreateOrganizationForm'

const FEATURES = [
  {
    icon: MapPin,
    title: 'GPS + QR verification',
    description: 'Real presence, checked on the backend — never guessed on a phone.',
  },
  {
    icon: Users,
    title: 'Live team dashboards',
    description: "See who's in, right now — not tomorrow's report.",
  },
  {
    icon: MonitorSmartphone,
    title: 'Walk-up kiosk displays',
    description: 'One shared QR screen at the door — no phone required.',
  },
]

/**
 * The one public, unauthenticated write surface in the whole app (see the
 * backend's own `POST /onboarding/tenants` docstring) — worth a real first
 * impression rather than a generic centered card. The marketing panel is
 * `hidden lg:flex`: on a phone the form is the only thing that matters.
 */
export default function CreateOrganizationPage() {
  return (
    <div className="flex min-h-screen">
      <div
        className="relative hidden w-[440px] shrink-0 flex-col justify-between overflow-hidden p-12 text-white lg:flex"
        style={{
          background: 'linear-gradient(160deg, var(--color-spotlight-from), var(--color-admin-700))',
        }}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-28 -top-24 size-96 rounded-full bg-white/5"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-36 -left-32 size-[420px] rounded-full bg-white/5"
        />

        <div className="relative z-10 flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-white/15 text-sm font-bold">K</span>
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold">Karya</span>
        </div>

        <div className="relative z-10">
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-semibold leading-tight text-balance">
            Attendance your team can trust, in three minutes.
          </h2>
          <ul className="mt-8 flex flex-col gap-5">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="flex items-start gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-white/15">
                  <feature.icon className="size-3.5" aria-hidden="true" />
                </span>
                <div>
                  <div className="text-sm font-semibold">{feature.title}</div>
                  <div className="mt-0.5 text-sm text-white/80">{feature.description}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative z-10 text-xs text-white/60">© Karya</div>
      </div>

      <div className="flex flex-1 items-center justify-center bg-surface p-6 sm:p-10">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex flex-col items-center gap-2 lg:hidden">
            <span className="flex size-10 items-center justify-center rounded-md bg-accent-600 text-base font-bold text-white">
              K
            </span>
          </div>

          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground">
            Create your organization
          </h1>
          <p className="mt-1 text-sm text-foreground-muted">
            You'll be the first admin — invite your team once you're in.
          </p>

          <div className="mt-6">
            <CreateOrganizationForm />
          </div>

          <p className="mt-6 text-center text-sm text-foreground-muted">
            Already have an organization on Karya?{' '}
            <Link to="/login" className="font-medium text-accent-600 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
