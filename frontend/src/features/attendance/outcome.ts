/**
 * Classifies the end of a check-in/check-out attempt into what the result
 * screen should say and, on failure, whether — and how — retrying makes
 * sense. Kept as a pure function so `CheckInOutFlow`'s branching is testable
 * without rendering anything.
 *
 * The retry rule follows directly from the backend's own ordering
 * (`app/services/presence/service.py::verify_presence`): the QR challenge is
 * consumed **only after** GPS has already passed, so a GPS-side refusal
 * (or a thrown network/server error, which by definition means the request
 * never got far enough to commit anything) leaves the same QR still valid —
 * retrying just needs a fresh location fix, not a re-scan. A QR-side
 * refusal means the code itself is the problem, so only a re-scan helps.
 */
import { describeError } from '@/lib/errors/describeError'
import { isApiError } from '@/lib/api/errors'
import { describeRefusalReason } from '@/features/attendance/reasonMessages'
import type { AttendanceActionResponse } from '@/lib/api/types'

const QR_REASONS = new Set(['QR_EXPIRED', 'QR_ALREADY_USED', 'QR_NOT_FOUND', 'QR_REVOKED', 'QR_NONCE_MISMATCH'])
const STATE_REASONS = new Set(['ALREADY_CHECKED_IN', 'NOT_CHECKED_IN'])

export type RetryTarget = 'scan' | 'gps' | null

export interface AttendanceOutcome {
  status: 'success' | 'refused' | 'error'
  title: string
  message: string
  retryTarget: RetryTarget
}

/** `settledResult` is either the resolved `AttendanceActionResponse` (which
 * may itself be a refusal — a 200 is not the same as success) or the thrown
 * error from a rejected mutation. */
export function resolveOutcome(settledResult: AttendanceActionResponse | unknown): AttendanceOutcome {
  if (isAttendanceActionResponse(settledResult)) {
    if (settledResult.success) {
      return { status: 'success', title: 'Success', message: '', retryTarget: null }
    }
    const reason = settledResult.reason ?? null
    const retryTarget: RetryTarget = reason && QR_REASONS.has(reason) ? 'scan' : reason && STATE_REASONS.has(reason) ? null : 'gps'
    return {
      status: 'refused',
      title: "That didn't go through",
      message: describeRefusalReason(reason),
      retryTarget,
    }
  }

  // Couldn't reach the server at all, or the server itself failed — never
  // shown as success, per §16.
  if (isApiError(settledResult) && settledResult.kind === 'network') {
    return {
      status: 'error',
      title: "Couldn't connect to Karya",
      message: 'Your attendance was not confirmed.',
      retryTarget: 'gps',
    }
  }

  const description = describeError(settledResult)
  const retryable = isApiError(settledResult) && settledResult.kind !== 'unauthorized'
  return {
    status: 'error',
    title: description.title,
    message: description.message,
    retryTarget: retryable ? 'gps' : null,
  }
}

function isAttendanceActionResponse(value: unknown): value is AttendanceActionResponse {
  return typeof value === 'object' && value !== null && 'success' in value && 'event_type' in value
}
