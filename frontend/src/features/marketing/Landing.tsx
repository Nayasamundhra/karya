import { CheckCircle2, Check, MapPin, QrCode } from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { BrandMark } from '@/features/marketing/BrandMark'
import { eyebrowClass } from '@/features/marketing/brandStyles'
import { cn } from '@/lib/utils/cn'

/**
 * The public home page. Everything on it is static marketing copy and links
 * to `/login` and `/onboarding` — there is no data fetching and no auth
 * dependency, so it is safe to render for a signed-out visitor before the
 * session bootstrap has resolved anything.
 *
 * Copy follows the brand voice: short, period-terminated, no exclamation
 * marks, claims limited to what the product actually does (see the root
 * CLAUDE.md "Load-bearing design decisions" for the attendance model these
 * sentences describe).
 */

const STEPS: { icon: ComponentType<{ className?: string }>; title: string; body: string }[] = [
  {
    icon: QrCode,
    title: 'Scan the office QR.',
    body: 'One printed code per location. It tells Karya which office the scan is for.',
  },
  {
    icon: MapPin,
    title: 'Location decides.',
    body: "The server checks the phone's position against your office. A photo of the code from home does not count.",
  },
  {
    icon: CheckCircle2,
    title: 'Recorded for good.',
    body: 'Every check-in and check-out is kept as an event. Nothing is edited. Nothing is deleted.',
  },
]

const ROLES = [
  { name: 'Staff', title: 'Check in in seconds.', body: 'Scan, confirm, go. See your own history and your hours for the week.' },
  { name: 'Managers', title: 'See who is in.', body: 'A live view of the team today, plus hours worked across the week.' },
  {
    name: 'Admins',
    title: 'Set it up once.',
    body: 'Add employees, place the office on the map, print the QR. A setup checklist walks you through.',
  },
]

const TRUST = [
  {
    title: 'Your data stays yours.',
    body: "Every organization is walled off. Nobody can look into another one's records.",
  },
  {
    title: 'Forgotten checkouts close themselves.',
    body: 'After your own shift limit, Karya adds a clearly marked check-out. The original is never rewritten.',
  },
  { title: 'Works as an app.', body: 'Install it from the browser on any phone. No app store needed.' },
]

function SectionHeading({ eyebrow, children, tone = 'light' }: { eyebrow: string; children: ReactNode; tone?: 'light' | 'dark' }) {
  return (
    <>
      <div className="mb-10 flex items-center gap-4">
        <span className={cn(eyebrowClass, tone === 'light' ? 'text-brand-purple-deep' : 'text-[#b794f6]')}>{eyebrow}</span>
        <div className={cn('h-px flex-1', tone === 'light' ? 'bg-brand-indigo/10' : 'bg-white/10')} />
      </div>
      <h2 className="mb-12 max-w-2xl font-brand text-4xl font-semibold leading-[1.1] tracking-tight text-balance sm:text-[44px]">
        {children}
      </h2>
    </>
  )
}

function ProductPreview() {
  return (
    <div className="relative flex flex-1 basis-[400px] justify-center">
      <div
        aria-hidden="true"
        className="absolute top-10 size-[380px] rounded-full bg-brand-purple/10 blur-[60px]"
      />
      <div className="relative w-full max-w-[400px] rounded-[32px] border border-brand-indigo/10 bg-white p-7 shadow-[0_32px_80px_rgba(10,10,11,0.2)]">
        <div className="flex items-center justify-between">
          <span className={cn(eyebrowClass, 'text-brand-indigo/60')}>Today</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#dcfce7] px-3 py-1.5 text-xs font-semibold text-[#166534]">
            <Check className="size-3" aria-hidden="true" strokeWidth={3} />
            At the office
          </span>
        </div>
        <div className="mt-5">
          <div className="text-[44px] font-semibold leading-none tracking-tight">09:02</div>
          <div className="mt-1 text-[15px] text-brand-indigo/60">Checked in at Acme Technologies</div>
        </div>
        <div className="my-5 h-px bg-brand-indigo/10" />
        <div className="flex gap-3">
          <div className="flex-1 rounded-2xl bg-brand-cream px-4 py-3.5">
            <div className={cn(eyebrowClass, 'text-brand-indigo/60')}>This week</div>
            <div className="mt-1 text-2xl font-semibold">31h 40m</div>
          </div>
          <div className="flex-1 rounded-2xl bg-brand-cream px-4 py-3.5">
            <div className={cn(eyebrowClass, 'text-brand-indigo/60')}>Days in</div>
            <div className="mt-1 text-2xl font-semibold">4 of 5</div>
          </div>
        </div>
        <div className="mt-5 flex h-13 items-center justify-center rounded-full bg-brand-ink text-base font-semibold text-white">
          Check out
        </div>
        <div className="absolute -bottom-12 -right-3 max-w-[220px] rounded-2xl border border-brand-gold bg-brand-gold-soft px-4 py-3 shadow-[0_8px_20px_rgba(10,10,11,0.08)] sm:-right-6">
          <div className={cn(eyebrowClass, 'text-brand-gold-deep')}>Auto-closed</div>
          <div className="mt-0.5 text-[13px] leading-snug text-brand-indigo">
            Yesterday's forgotten checkout was closed at shift end.
          </div>
        </div>
      </div>
    </div>
  )
}

export function Landing() {
  return (
    <div className="theme-brand flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-[1280px] flex-wrap items-center justify-between gap-4 px-6 py-5 sm:px-12">
        <BrandMark />
        <nav aria-label="Sections" className="order-3 hidden items-center gap-7 text-[15px] text-brand-indigo/70 md:order-none md:flex">
          <a href="#how" className="py-2 hover:text-brand-indigo">How it works</a>
          <a href="#roles" className="py-2 hover:text-brand-indigo">Who it is for</a>
          <a href="#trust" className="py-2 hover:text-brand-indigo">Trust</a>
        </nav>
        <div className="flex items-center gap-3">
          <Button asChild variant="brandOutline">
            <Link to="/login">Log in</Link>
          </Button>
          <Button asChild variant="brand">
            <Link to="/onboarding">Sign up</Link>
          </Button>
        </div>
      </header>

      <main>
        <section className="mx-auto flex w-full max-w-[1280px] flex-wrap items-center gap-16 px-6 pb-24 pt-14 sm:px-12 sm:pt-[72px]">
          <div className="flex min-w-0 flex-1 basis-[480px] flex-col gap-7">
            <span className={cn(eyebrowClass, 'text-brand-purple-deep')}>Attendance for teams that work on site</span>
            <h1 className="font-brand text-5xl font-semibold leading-[1.05] tracking-tight text-balance sm:text-[68px]">
              Attendance you can trust.
            </h1>
            <p className="max-w-[520px] text-xl leading-normal text-brand-indigo/65 text-pretty">
              Staff scan the office QR. Karya checks the phone is actually there. Managers see who is in, without
              chasing anyone. Fast.
            </p>
            <div className="mt-2 flex flex-wrap gap-3">
              <Button asChild variant="brand" size="xl">
                <Link to="/onboarding">Create your organization</Link>
              </Button>
              <Button asChild variant="brandOutline" size="xl">
                <Link to="/login">Log in</Link>
              </Button>
            </div>
            <p className="text-[13px] text-brand-indigo/65">
              Already have an organization ID? Log in with it, your email and your password.
            </p>
          </div>
          <ProductPreview />
        </section>

        <section id="how" className="mx-auto w-full max-w-[1280px] scroll-mt-8 px-6 pb-24 pt-8 sm:px-12">
          <SectionHeading eyebrow="How it works">Scan. Verify. Done.</SectionHeading>
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map((step, index) => (
              <li
                key={step.title}
                className="flex flex-col gap-4 rounded-3xl border border-brand-indigo/10 bg-white p-8 shadow-sm transition duration-500 hover:-translate-y-2 hover:border-brand-indigo/20 hover:shadow-md"
              >
                <span className="flex size-14 items-center justify-center rounded-2xl bg-brand-lilac text-brand-purple-deep">
                  <step.icon className="size-7" aria-hidden="true" />
                </span>
                <span className={cn(eyebrowClass, 'text-brand-indigo/60')}>{String(index + 1).padStart(2, '0')}</span>
                <h3 className="text-2xl font-semibold tracking-tight">{step.title}</h3>
                <p className="text-[15px] leading-normal text-brand-indigo/65">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="roles" className="scroll-mt-8 bg-brand-ink text-white">
          <div className="mx-auto w-full max-w-[1280px] px-6 py-24 sm:px-12">
            <SectionHeading eyebrow="Who it is for" tone="dark">
              One tool. Three jobs.
            </SectionHeading>
            <div className="grid gap-6 md:grid-cols-3">
              {ROLES.map((role) => (
                <div key={role.name} className="flex flex-col gap-3 rounded-3xl border border-white/5 bg-brand-ink-raised p-8">
                  <span className={cn(eyebrowClass, 'text-brand-gold')}>{role.name}</span>
                  <h3 className="text-2xl font-semibold tracking-tight">{role.title}</h3>
                  <p className="text-[15px] leading-normal text-white/65">{role.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="trust" className="mx-auto w-full max-w-[1280px] scroll-mt-8 px-6 py-24 sm:px-12">
          <div className="mb-10 flex items-center gap-4">
            <span className={cn(eyebrowClass, 'text-brand-purple-deep')}>Trust</span>
            <div className="h-px flex-1 bg-brand-indigo/10" />
          </div>
          <div className="grid gap-12 md:grid-cols-3">
            {TRUST.map((item) => (
              <div key={item.title} className="flex flex-col gap-2">
                <h3 className="text-xl font-semibold">{item.title}</h3>
                <p className="text-[15px] leading-normal text-brand-indigo/65">{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto w-full max-w-[1280px] px-6 pb-24 sm:px-12">
          <div className="flex flex-wrap items-center justify-between gap-8 rounded-[32px] bg-brand-plum p-8 sm:p-16">
            <h2 className="max-w-[560px] font-brand text-4xl font-semibold leading-[1.1] tracking-tight text-white text-balance sm:text-[44px]">
              Start with your office. Add the team after.
            </h2>
            <div className="flex flex-wrap gap-3">
              <Button asChild variant="brandGold" size="xl">
                <Link to="/onboarding">Sign up</Link>
              </Button>
              <Button asChild variant="brandOnDark" size="xl">
                <Link to="/login">Log in</Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="mt-auto border-t border-brand-indigo/10">
        <div className="mx-auto flex w-full max-w-[1280px] flex-wrap items-center justify-between gap-4 px-6 py-8 sm:px-12">
          <span className="text-[13px] font-semibold uppercase tracking-[0.2em]">Karya</span>
          <span className="text-[13px] text-brand-indigo/65">Attendance, verified.</span>
        </div>
      </footer>
    </div>
  )
}
