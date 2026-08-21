import { RouterProvider } from 'react-router-dom'

import { AppProviders } from '@/app/providers'
import { router } from '@/app/router'
import { ErrorBoundary } from '@/components/layout/ErrorBoundary'

export function App() {
  return (
    <ErrorBoundary>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </ErrorBoundary>
  )
}
