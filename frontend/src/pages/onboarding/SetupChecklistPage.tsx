import { Check, MapPin, MonitorSmartphone, PartyPopper, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { useAuth } from '@/features/auth/useAuth'
import { useSetupStatus, type SetupStep } from '@/features/onboarding/useSetupStatus'

const STEP_ICON: Record<SetupStep['id'], LucideIcon> = {
  location: MapPin,
  display: MonitorSmartphone,
  employees: Users,
}

/**
 * PRD §6's "Welcome to Karya" checklist: the screen a fresh tenant admin
 * lands on right after email verification, and can return to any time via
 * Home until every step is done. `useSetupStatus` derives each item's
 * done/not-done state from the same data its target page already fetches —
 * this page adds no new backend surface, only a summary view of it.
 */
export default function SetupChecklistPage() {
  const { user } = useAuth()
  const { isLoading, steps, isComplete } = useSetupStatus()
  const doneCount = steps.filter((step) => step.done).length

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <div className="text-xs font-semibold uppercase tracking-widest text-admin-600">Welcome to Karya</div>
        <h1 className="mt-1 font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground sm:text-3xl">
          Let's finish setting up{user ? `, ${user.name}` : ''}
        </h1>
        <p className="mt-1.5 text-sm text-foreground-muted">
          Three steps, and your team can start checking in. You can always come back to this from Home.
        </p>
      </div>

      {!isLoading && (
        <div className="flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border">
            <div
              className="h-full bg-admin-600 transition-[width]"
              style={{ width: `${(doneCount / steps.length) * 100}%` }}
            />
          </div>
          <span className="shrink-0 text-xs font-semibold text-foreground-muted">
            {doneCount} of {steps.length} complete
          </span>
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-[76px] w-full rounded-lg" />
          <Skeleton className="h-[76px] w-full rounded-lg" />
          <Skeleton className="h-[76px] w-full rounded-lg" />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {/* Always true by the time this authenticated screen renders at
           * all — shown as already-done rather than omitted, so the
           * checklist reads as real progress made, not three more chores. */}
          <DoneItem label="Organization created" />
          <DoneItem label="Email verified" />
          {steps.map((step) => (
            <ChecklistItem key={step.id} step={step} />
          ))}
        </div>
      )}

      {!isLoading && isComplete && (
        <Alert variant="success" title="You're ready!">
          <div className="flex items-center gap-2">
            <PartyPopper className="size-4 shrink-0" aria-hidden="true" />
            <span>Setup is complete — employees can check in from their phones.</span>
          </div>
        </Alert>
      )}

      <div>
        <Button asChild variant="secondary">
          <Link to="/">Go to Home</Link>
        </Button>
      </div>
    </div>
  )
}

function DoneItem({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4 sm:p-5">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-success-50 text-success-700">
          <Check className="size-5" aria-hidden="true" />
        </span>
        <p className="text-sm font-medium text-foreground-muted line-through">{label}</p>
      </CardContent>
    </Card>
  )
}

function ChecklistItem({ step }: { step: SetupStep }) {
  const Icon = STEP_ICON[step.id]

  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4 sm:p-5">
        <span
          className={
            step.done
              ? 'flex size-10 shrink-0 items-center justify-center rounded-lg bg-success-50 text-success-700'
              : 'flex size-10 shrink-0 items-center justify-center rounded-lg bg-admin-50 text-admin-700'
          }
        >
          {step.done ? (
            <Check className="size-5" aria-hidden="true" />
          ) : (
            <Icon className="size-5" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className={step.done ? 'text-sm font-medium text-foreground-muted line-through' : 'text-sm font-medium text-foreground'}>
            {step.label}
          </p>
        </div>
        {!step.done && (
          <Button asChild variant="secondary" size="sm" className="shrink-0">
            <Link to={step.to}>{step.cta}</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
