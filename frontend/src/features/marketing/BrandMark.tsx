import { Link } from 'react-router-dom'

import { cn } from '@/lib/utils/cn'

interface BrandMarkProps {
  /** `dark` is for use on a plum/ink surface: the tile flips to gold. */
  tone?: 'light' | 'dark'
  className?: string
}

/**
 * The Karya wordmark on public pages — a plum tile with a gold "K" and the
 * name set in the brand's wide-tracked, uppercase label style. Links home
 * (`/`), which for a signed-out visitor is the landing page and for a
 * signed-in one is their dashboard, so it is never a dead end.
 */
export function BrandMark({ tone = 'light', className }: BrandMarkProps) {
  return (
    <Link to="/" aria-label="Karya home" className={cn('inline-flex items-center gap-3', className)}>
      <span
        aria-hidden="true"
        className={cn(
          'flex size-9 items-center justify-center rounded-xl text-lg font-semibold',
          tone === 'light' ? 'bg-brand-plum text-brand-gold' : 'bg-brand-gold text-brand-plum',
        )}
      >
        K
      </span>
      <span className="text-sm font-semibold uppercase tracking-[0.2em]">Karya</span>
    </Link>
  )
}
