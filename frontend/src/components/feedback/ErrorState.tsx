import { AlertCircle } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { describeError } from '@/lib/errors/describeError'
import { cn } from '@/lib/utils/cn'

export interface ErrorStateProps {
  error: unknown
  onRetry?: () => void
  className?: string
}

/** For "a request failed" — see `EmptyState` for "there is nothing here".
 * Never auto-retries: retrying a security-sensitive mutation (attendance,
 * password change) on its own would be exactly the kind of surprising
 * double-submit §19 warns against — a human always presses the button. */
export function ErrorState({ error, onRetry, className }: ErrorStateProps) {
  const description = describeError(error)

  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center gap-3 rounded-lg border border-danger-500/30 bg-danger-50 p-8 text-center', className)}
    >
      <AlertCircle className="size-8 text-danger-600" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-danger-700">{description.title}</p>
        <p className="text-sm text-danger-700/80">{description.message}</p>
        {description.requestId && (
          <p className="mt-1 text-xs text-danger-700/60">Reference: {description.requestId}</p>
        )}
      </div>
      {description.retryable && onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
