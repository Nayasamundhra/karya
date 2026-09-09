import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as tenantApi from '@/lib/api/endpoints/tenant'
import type { AttendanceLocationCreateRequest, AttendanceLocationUpdateRequest } from '@/lib/api/types'

export function useCreateLocation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AttendanceLocationCreateRequest) => tenantApi.createOwnLocation(payload),
    onSuccess: (created) => {
      queryClient.setQueryData(['tenant', 'location'], created)
    },
  })
}

export function useUpdateLocation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AttendanceLocationUpdateRequest) => tenantApi.updateOwnLocation(payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(['tenant', 'location'], updated)
    },
  })
}
