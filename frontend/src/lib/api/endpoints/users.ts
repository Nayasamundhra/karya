import { apiFetch } from '@/lib/api/client'
import type {
  PasswordChangeRequest,
  PasswordChangeResponse,
  RoleUpdateRequest,
  SelfUpdateRequest,
  UserAuditResponse,
  UserCreateRequest,
  UserDetailResponse,
  UserListResponse,
  UserResponse,
  UserRole,
  UserStatus,
  UserUpdateRequest,
} from '@/lib/api/types'

// --- Self-service --------------------------------------------------------

export function getOwnProfile(signal?: AbortSignal): Promise<UserResponse> {
  return apiFetch<UserResponse>('/api/v1/users/me', { signal })
}

export function updateOwnProfile(payload: SelfUpdateRequest): Promise<UserResponse> {
  return apiFetch<UserResponse>('/api/v1/users/me', { method: 'PATCH', body: payload })
}

export function changeOwnPassword(payload: PasswordChangeRequest): Promise<PasswordChangeResponse> {
  return apiFetch<PasswordChangeResponse>('/api/v1/users/me/password', { method: 'POST', body: payload })
}

// --- Administration (TENANT_ADMIN only) ----------------------------------

export interface ListUsersQuery {
  search?: string
  role?: UserRole
  status?: UserStatus
  page?: number
  pageSize?: number
}

export function listUsers(params: ListUsersQuery = {}, signal?: AbortSignal): Promise<UserListResponse> {
  return apiFetch<UserListResponse>('/api/v1/users', {
    query: {
      search: params.search,
      role: params.role,
      status: params.status,
      page: params.page,
      page_size: params.pageSize,
    },
    signal,
  })
}

export function createUser(payload: UserCreateRequest): Promise<UserDetailResponse> {
  return apiFetch<UserDetailResponse>('/api/v1/users', { method: 'POST', body: payload })
}

export function getUser(userId: string, signal?: AbortSignal): Promise<UserDetailResponse> {
  return apiFetch<UserDetailResponse>(`/api/v1/users/${userId}`, { signal })
}

export function updateUser(userId: string, payload: UserUpdateRequest): Promise<UserDetailResponse> {
  return apiFetch<UserDetailResponse>(`/api/v1/users/${userId}`, { method: 'PATCH', body: payload })
}

export function changeUserRole(userId: string, payload: RoleUpdateRequest): Promise<UserDetailResponse> {
  return apiFetch<UserDetailResponse>(`/api/v1/users/${userId}/role`, { method: 'PATCH', body: payload })
}

export function activateUser(userId: string): Promise<UserDetailResponse> {
  return apiFetch<UserDetailResponse>(`/api/v1/users/${userId}/activate`, { method: 'POST' })
}

export function deactivateUser(userId: string): Promise<UserDetailResponse> {
  return apiFetch<UserDetailResponse>(`/api/v1/users/${userId}/deactivate`, { method: 'POST' })
}

export function getUserAudit(
  userId: string,
  params: { page?: number; pageSize?: number } = {},
  signal?: AbortSignal,
): Promise<UserAuditResponse> {
  return apiFetch<UserAuditResponse>(`/api/v1/users/${userId}/audit`, {
    query: { page: params.page, page_size: params.pageSize },
    signal,
  })
}
