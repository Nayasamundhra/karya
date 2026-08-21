import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as tenantApi from '@/lib/api/endpoints/tenant'
import type { TenantUpdateRequest } from '@/lib/api/types'

export function useUpdateTenant() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: TenantUpdateRequest) => tenantApi.updateOwnTenant(payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(['tenant', 'me'], updated)
    },
  })
}
