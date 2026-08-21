import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useEffect, useState } from 'react'

import { Toaster } from '@/components/ui/Toaster'
import { FullScreenSpinner } from '@/components/layout/FullScreenSpinner'
import { onSessionCleared, bootstrapSession } from '@/lib/auth/session'

// `import.meta.env.DEV` is a build-time constant Vite inlines and dead-code
// eliminates — in a production build this whole ternary collapses to `null`
// and the dynamic import is never emitted, so `@tanstack/react-query-devtools`
// never reaches the shipped bundle (confirmed in `docs/performance.md`'s
// bundle-size table: it does not appear in any production chunk).
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((mod) => ({ default: mod.ReactQueryDevtools })),
    )
  : null

/**
 * One `QueryClient` for the app's lifetime. Defaults are conservative
 * (§22): a short `staleTime` rather than `0`/`Infinity` for most data, one
 * retry (a second identical request rarely succeeds where the first
 * `ApiError` was 401/403/404/422 — see the retry guard below), and no
 * automatic mutation retries (§19: nothing here should silently resubmit a
 * write). Any query with materially different freshness needs — attendance
 * status chief among them once Phase 9 lands — sets its own `staleTime`
 * rather than fighting this default; see `useTenant` for that pattern with
 * the opposite need (a *longer* stale time).
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          const apiError = error as { kind?: string } | undefined
          if (apiError?.kind && ['unauthorized', 'forbidden', 'not_found', 'validation'].includes(apiError.kind)) {
            return false
          }
          return failureCount < 1
        },
      },
      mutations: {
        retry: false,
      },
    },
  })
}

/**
 * Runs `bootstrapSession` exactly once and blocks rendering the rest of the
 * app until it settles — every route's `RequireAuth` depends on
 * `authStore.status` already being `authenticated`/`unauthenticated`, never
 * still `loading`, by the time it first checks.
 */
function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    void bootstrapSession().finally(() => setReady(true))
  }, [])

  if (!ready) return <FullScreenSpinner label="Loading Karya…" />
  return <>{children}</>
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient)

  useEffect(() => onSessionCleared(() => queryClient.clear()), [queryClient])

  return (
    <QueryClientProvider client={queryClient}>
      <AuthBootstrap>{children}</AuthBootstrap>
      <Toaster />
      {ReactQueryDevtools && (
        <Suspense fallback={null}>
          <ReactQueryDevtools initialIsOpen={false} />
        </Suspense>
      )}
    </QueryClientProvider>
  )
}
