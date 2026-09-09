import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as displayApi from '@/lib/api/endpoints/display'
import type { DisplayTokenCreateRequest } from '@/lib/api/types'

export function useCreateDisplayToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: DisplayTokenCreateRequest) => displayApi.createDisplayToken(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', 'display-tokens'] })
    },
  })
}

export function useRevokeDisplayToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (displayTokenId: string) => displayApi.revokeDisplayToken(displayTokenId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', 'display-tokens'] })
    },
  })
}
