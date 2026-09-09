/**
 * A quiet, in-context reminder of what's left to configure — reusing
 * `useSetupStatus` (the same data `SetupChecklistPage` and `HomePage`'s
 * `SetupNudge` read), shown right where an admin is already configuring
 * things rather than only as a separate alert. Deliberately not
 * alert-colored: this is progress, not a warning. Renders nothing once
 * every step is done, same as `SetupNudge`.
 */
import { Check } from 'lucide-react'

import { Skeleton } from '@/components/ui/Skeleton'
import { useSetupStatus } from '@/features/onboarding/useSetupStatus'
import { cn } from '@/lib/utils/cn'

export function SetupProgressStrip() {
  const { isLoading, steps, isComplete } = useSetupStatus()

  if (isLoading) return <Skeleton className="h-16 w-full rounded-lg" />
  if (isComplete) return null

  const doneCount = steps.filter((step) => step.done).length

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface-raised p-4 sm:flex-row sm:items-center sm:gap-6">
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-sm font-semibold text-foreground">
          Setup · {doneCount} of {steps.length} complete
        </span>
        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-border">
          <div
            className="h-full bg-admin-600 transition-[width]"
            style={{ width: `${(doneCount / steps.length) * 100}%` }}
          />
        </div>
      </div>

      <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
        {steps.map((step) => (
          <li
            key={step.id}
            className={cn(
              'flex items-center gap-1.5 text-xs',
              step.done ? 'text-success-700' : 'font-medium text-admin-700',
            )}
          >
            {step.done ? (
              <Check className="size-3.5 shrink-0" aria-hidden="true" />
            ) : (
              <span className="size-3.5 shrink-0 rounded-full border-2 border-current" aria-hidden="true" />
            )}
            {step.label}
          </li>
        ))}
      </ul>
    </div>
  )
}
