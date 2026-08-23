import { describe, expect, it } from 'vitest'

import { ApiError } from '@/lib/api/errors'
import { resolveOutcome } from '@/features/attendance/outcome'
import type { AttendanceActionResponse } from '@/lib/api/types'

function successResponse(overrides: Partial<AttendanceActionResponse> = {}): AttendanceActionResponse {
  return {
    success: true,
    event_type: 'CHECK_IN',
    status: 'CHECKED_IN',
    attendance_event_id: 'event-1',
    event_timestamp: '2026-08-22T09:04:00Z',
    presence: null,
    reason: null,
    ...overrides,
  }
}

function refusal(reason: string): AttendanceActionResponse {
  return {
    success: false,
    event_type: 'CHECK_IN',
    status: 'NOT_CHECKED_IN',
    attendance_event_id: null,
    event_timestamp: null,
    presence: null,
    reason,
  }
}

describe('resolveOutcome', () => {
  it('reports success only for success: true — never for a thrown error or a refusal', () => {
    expect(resolveOutcome(successResponse()).status).toBe('success')
    expect(resolveOutcome(refusal('OUTSIDE_GEOFENCE')).status).toBe('refused')
    expect(resolveOutcome(new ApiError({ kind: 'network', message: 'x' })).status).toBe('error')
  })

  it('sends a QR-side refusal back to scanning, since the QR itself is the problem', () => {
    for (const reason of ['QR_EXPIRED', 'QR_ALREADY_USED', 'QR_NOT_FOUND', 'QR_REVOKED', 'QR_NONCE_MISMATCH']) {
      expect(resolveOutcome(refusal(reason)).retryTarget).toBe('scan')
    }
  })

  it('sends a GPS-side refusal back to the GPS stage — the QR was never consumed, per the backend\'s own ordering', () => {
    for (const reason of ['OUTSIDE_GEOFENCE', 'GPS_ACCURACY_TOO_LOW', 'GPS_INVALID', 'NO_ACTIVE_ATTENDANCE_LOCATION']) {
      expect(resolveOutcome(refusal(reason)).retryTarget).toBe('gps')
    }
  })

  it('offers no retry for a state-conflict refusal — retrying the same action would just refuse again', () => {
    expect(resolveOutcome(refusal('ALREADY_CHECKED_IN')).retryTarget).toBeNull()
    expect(resolveOutcome(refusal('NOT_CHECKED_IN')).retryTarget).toBeNull()
  })

  it('gives a network failure the exact "not confirmed" copy from the phase brief, and allows retry', () => {
    const outcome = resolveOutcome(new ApiError({ kind: 'network', message: 'irrelevant raw message' }))
    expect(outcome.title).toBe("Couldn't connect to Karya")
    expect(outcome.message).toBe('Your attendance was not confirmed.')
    expect(outcome.retryTarget).toBe('gps')
  })

  it('never offers a retry after a session expiry — the guard will redirect instead', () => {
    const outcome = resolveOutcome(new ApiError({ kind: 'unauthorized', message: 'Session expired', status: 401 }))
    expect(outcome.retryTarget).toBeNull()
  })

  it('allows retry after a rate limit or server error', () => {
    expect(resolveOutcome(new ApiError({ kind: 'rate_limited', message: 'x', status: 429 })).retryTarget).toBe('gps')
    expect(resolveOutcome(new ApiError({ kind: 'server', message: 'x', status: 500 })).retryTarget).toBe('gps')
  })
})
