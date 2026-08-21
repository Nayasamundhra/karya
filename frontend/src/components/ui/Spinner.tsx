import { Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils/cn'

interface SpinnerProps {
  className?: string
  /** Visible label for sighted users who want one; always announced to screen readers regardless. */
  label?: string
}

/** A spinner communicates "working" visually — it must never be the only
 * thing a screen-reader user gets, so the accessible name is always present
 * even when `label` (the visible caption) is omitted. */
export function Spinner({ className, label }: SpinnerProps) {
  return (
    <span role="status" className="inline-flex items-center gap-2">
      <Loader2 className={cn('size-4 animate-spin text-foreground-muted', className)} aria-hidden="true" />
      <span className={label ? undefined : 'sr-only'}>{label ?? 'Loading'}</span>
    </span>
  )
}
