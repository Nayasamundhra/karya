import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'

/**
 * Reached only via `RequireRole` steering a signed-in user away from a
 * route their role doesn't list — a UX nicety. It is not the security
 * boundary: hitting the underlying API directly with the wrong role gets a
 * 403 from the backend regardless of whether this page exists.
 */
export default function ForbiddenPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-4 text-center">
      <p className="text-sm font-medium text-foreground-muted">403</p>
      <h1 className="text-xl font-semibold text-foreground">You don't have permission</h1>
      <p className="max-w-sm text-sm text-foreground-muted">
        This page needs a different role. Contact your administrator if this seems wrong.
      </p>
      <Button asChild>
        <Link to="/">Go home</Link>
      </Button>
    </div>
  )
}
