import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

/** A `QueryClient` tuned for tests: no retries (so a mocked rejection
 * resolves the query to an error state immediately instead of after
 * Vitest's default multi-second retry backoff) and no window-focus
 * refetching (jsdom has no real focus/blur lifecycle worth reacting to). */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
}

export function TestQueryProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
}
