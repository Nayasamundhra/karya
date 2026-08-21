import { apiFetch } from '@/lib/api/client'

interface ProbeResponse {
  status: string
}

/** Liveness — never useful to call from the UI, kept for completeness/tests. */
export function health(signal?: AbortSignal): Promise<ProbeResponse> {
  return apiFetch<ProbeResponse>('/health', { auth: false, signal })
}

/** Readiness — used by the "backend unavailable" banner, not by any auth flow. */
export function ready(signal?: AbortSignal): Promise<ProbeResponse> {
  return apiFetch<ProbeResponse>('/ready', { auth: false, signal })
}
