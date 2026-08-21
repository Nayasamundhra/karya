import { cn } from '@/lib/utils/cn'

/**
 * A plain, semantic `<table>` wrapped in its own horizontal scroll
 * container — the container scrolls, never the page (see §10: the body must
 * never overflow horizontally). This is the right shape for tabular data
 * that is genuinely tabular (a manager's team roster, a user list). For
 * data that reads better as cards on a phone than as a horizontally-scrolled
 * table, build a card list instead and reserve `Table` for the desktop
 * breakpoint — that decision belongs to the feature, not to this primitive.
 */
export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border">
      <table className={cn('w-full caption-bottom text-sm', className)} {...props} />
    </div>
  )
}

export function TableHeader({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn('bg-surface-sunken', className)} {...props} />
}

export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn('divide-y divide-border', className)} {...props} />
}

export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn('hover:bg-surface-sunken/60', className)} {...props} />
}

export function TableHead({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn('h-11 whitespace-nowrap px-4 text-left align-middle font-medium text-foreground-muted', className)}
      {...props}
    />
  )
}

export function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('whitespace-nowrap px-4 py-3 align-middle text-foreground', className)} {...props} />
}

export function TableCaption({ className, ...props }: React.HTMLAttributes<HTMLTableCaptionElement>) {
  return <caption className={cn('mt-2 text-sm text-foreground-muted', className)} {...props} />
}
