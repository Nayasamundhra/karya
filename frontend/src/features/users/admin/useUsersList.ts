import { useQuery } from '@tanstack/react-query'

import * as usersApi from '@/lib/api/endpoints/users'
import type { ListUsersQuery } from '@/lib/api/endpoints/users'
import { adminUserKeys } from '@/features/users/admin/queryKeys'

/** The tenant's employee list/search (TENANT_ADMIN only — enforced
 * server-side). `placeholderData` keeps the previous page/results on screen
 * while a new search or page loads instead of flashing to a loading state. */
export function useUsersList(params: ListUsersQuery = {}) {
  return useQuery({
    queryKey: adminUserKeys.list(params),
    queryFn: ({ signal }) => usersApi.listUsers(params, signal),
    placeholderData: (previous) => previous,
  })
}
