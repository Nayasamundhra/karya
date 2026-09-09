import { apiFetch } from '@/lib/api/client'
import type {
  AttendanceLocationCreateRequest,
  AttendanceLocationResponse,
  AttendanceLocationUpdateRequest,
  TenantResponse,
  TenantUpdateRequest,
} from '@/lib/api/types'

export function getOwnTenant(signal?: AbortSignal): Promise<TenantResponse> {
  return apiFetch<TenantResponse>('/api/v1/tenant/me', { signal })
}

/** TENANT_ADMIN only. */
export function updateOwnTenant(payload: TenantUpdateRequest): Promise<TenantResponse> {
  return apiFetch<TenantResponse>('/api/v1/tenant/me', { method: 'PATCH', body: payload })
}

/** Throws a `not_found` ApiError if no location has been set up yet. */
export function getOwnLocation(signal?: AbortSignal): Promise<AttendanceLocationResponse> {
  return apiFetch<AttendanceLocationResponse>('/api/v1/tenant/me/location', { signal })
}

/** TENANT_ADMIN only. Throws a `conflict` ApiError if one already exists. */
export function createOwnLocation(
  payload: AttendanceLocationCreateRequest,
): Promise<AttendanceLocationResponse> {
  return apiFetch<AttendanceLocationResponse>('/api/v1/tenant/me/location', {
    method: 'POST',
    body: payload,
  })
}

/** TENANT_ADMIN only. Throws a `not_found` ApiError if none exists yet. */
export function updateOwnLocation(
  payload: AttendanceLocationUpdateRequest,
): Promise<AttendanceLocationResponse> {
  return apiFetch<AttendanceLocationResponse>('/api/v1/tenant/me/location', {
    method: 'PATCH',
    body: payload,
  })
}
