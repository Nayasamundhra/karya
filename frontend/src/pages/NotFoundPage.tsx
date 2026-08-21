import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-4 text-center">
      <p className="text-sm font-medium text-foreground-muted">404</p>
      <h1 className="text-xl font-semibold text-foreground">Page not found</h1>
      <p className="max-w-sm text-sm text-foreground-muted">
        The page you're looking for doesn't exist, or you don't have access to it.
      </p>
      <Button asChild>
        <Link to="/">Go home</Link>
      </Button>
    </div>
  )
}
