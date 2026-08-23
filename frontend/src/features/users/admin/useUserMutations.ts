/**
 * Employee-management mutations (§11–§14, §20) — one hook per backend
 * action, each invalidating only the affected query (the employee list) on
 * success. No optimistic updates: the UI reflects the backend's response,
 * never a claimed-in-advance state (§13).
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as usersApi from '@/lib/api/endpoints/users'
import type { RoleUpdateRequest, UserCreateRequest, UserUpdateRequest } from '@/lib/api/types'
import { adminUserKeys } from '@/features/users/admin/queryKeys'

function useInvalidateEmployeeList() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: adminUserKeys.all })
}

export function useCreateEmployee() {
  const invalidate = useInvalidateEmployeeList()
  return useMutation({
    mutationFn: (payload: UserCreateRequest) => usersApi.createUser(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateEmployee() {
  const invalidate = useInvalidateEmployeeList()
  return useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: UserUpdateRequest }) =>
      usersApi.updateUser(userId, payload),
    onSuccess: invalidate,
  })
}

export function useChangeEmployeeRole() {
  const invalidate = useInvalidateEmployeeList()
  return useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: RoleUpdateRequest }) =>
      usersApi.changeUserRole(userId, payload),
    onSuccess: invalidate,
  })
}

export function useActivateEmployee() {
  const invalidate = useInvalidateEmployeeList()
  return useMutation({
    mutationFn: (userId: string) => usersApi.activateUser(userId),
    onSuccess: invalidate,
  })
}

export function useDeactivateEmployee() {
  const invalidate = useInvalidateEmployeeList()
  return useMutation({
    mutationFn: (userId: string) => usersApi.deactivateUser(userId),
    onSuccess: invalidate,
  })
}
