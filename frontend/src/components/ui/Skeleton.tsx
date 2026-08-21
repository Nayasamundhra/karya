import { cn } from '@/lib/utils/cn'

/** A shaped placeholder, sized like the content it stands in for, so nothing
 * jumps when real content replaces it. Prefer this over a spinner whenever
 * the eventual layout is known ahead of time — see `docs/loading-states.md`. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-surface-sunken', className)}
      aria-hidden="true"
      {...props}
    />
  )
}
