import { describe, expect, it } from 'vitest'

import { describeRefusalReason } from '@/features/attendance/reasonMessages'

describe('describeRefusalReason', () => {
  it('maps every documented backend refusal reason to the phase-brief copy', () => {
    expect(describeRefusalReason('QR_EXPIRED')).toMatch(/expired/i)
    expect(describeRefusalReason('QR_ALREADY_USED')).toMatch(/already been used/i)
    expect(describeRefusalReason('OUTSIDE_GEOFENCE')).toMatch(/outside the office area/i)
    expect(describeRefusalReason('GPS_ACCURACY_TOO_LOW')).toMatch(/clearer GPS signal/i)
    expect(describeRefusalReason('ALREADY_CHECKED_IN')).toMatch(/already checked in/i)
    expect(describeRefusalReason('NOT_CHECKED_IN')).toMatch(/not currently checked in/i)
  })

  it('gives QR_NOT_FOUND and QR_NONCE_MISMATCH the same "invalid code" message a spoofed/mismatched id gets', () => {
    // QR_TENANT_MISMATCH / QR_LOCATION_MISMATCH never reach the client — the
    // backend collapses them to QR_NOT_FOUND — so this only needs to cover
    // what can actually arrive.
    expect(describeRefusalReason('QR_NOT_FOUND')).toBe(describeRefusalReason('QR_NONCE_MISMATCH'))
  })

  it('falls back to a generic message for an unmapped or missing reason, never rendering undefined', () => {
    expect(describeRefusalReason(null)).toBeTruthy()
    expect(describeRefusalReason(undefined)).toBeTruthy()
    expect(describeRefusalReason('SOME_FUTURE_REASON')).toBeTruthy()
  })
})
