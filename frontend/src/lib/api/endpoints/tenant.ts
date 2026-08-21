import { apiFetch } from '@/lib/api/client'
import type { TenantResponse, TenantUpdateRequest } from '@/lib/api/types'

export function getOwnTenant(signal?: AbortSignal): Promise<TenantResponse> {
  return apiFetch<TenantResponse>('/api/v1/tenant/me', { signal })
}

/** TENANT_ADMIN only. */
export function updateOwnTenant(payload: TenantUpdateRequest): Promise<TenantResponse> {
  return apiFetch<TenantResponse>('/api/v1/tenant/me', { method: 'PATCH', body: payload })
}
