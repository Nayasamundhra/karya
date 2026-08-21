import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import * as usersApi from '@/lib/api/endpoints/users'
import type { SelfUpdateRequest } from '@/lib/api/types'
import { useAuthStore } from '@/stores/authStore'

const PROFILE_QUERY_KEY = ['users', 'me'] as const

export function useOwnProfile() {
  return useQuery({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: ({ signal }) => usersApi.getOwnProfile(signal),
  })
}

export function useUpdateOwnProfile() {
  const queryClient = useQueryClient()
  const setUser = useAuthStore((state) => state.setUser)

  return useMutation({
    mutationFn: (payload: SelfUpdateRequest) => usersApi.updateOwnProfile(payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(PROFILE_QUERY_KEY, updated)
      // Keep the session's copy (used by the shell's greeting/avatar) in
      // sync too, so a name change is reflected immediately without a
      // full `/auth/me` refetch.
      setUser(updated)
    },
  })
}
