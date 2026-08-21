import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils/cn'

export interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: { label: string; onClick: () => void }
  className?: string
}

/** For "there is nothing here yet" — distinct from `ErrorState`, which is
 * for "something went wrong trying to find out". Conflating the two tells a
 * user their data is missing when the real problem was a failed request. */
export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center gap-3 rounded-lg border border-dashed border-border p-8 text-center', className)}>
      <Icon className="size-8 text-foreground-muted" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && <p className="text-sm text-foreground-muted">{description}</p>}
      </div>
      {action && (
        <Button variant="secondary" size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
