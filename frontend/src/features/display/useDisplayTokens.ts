import { useQuery } from '@tanstack/react-query'

import * as displayApi from '@/lib/api/endpoints/display'
import { useAuth } from '@/features/auth/useAuth'

export function useDisplayTokens() {
  const { isAuthenticated } = useAuth()
  return useQuery({
    queryKey: ['tenant', 'display-tokens'],
    queryFn: ({ signal }) => displayApi.listDisplayTokens(signal),
    enabled: isAuthenticated,
  })
}
