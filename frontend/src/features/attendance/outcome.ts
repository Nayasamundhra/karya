/**
 * Classifies the end of a check-in/check-out attempt into what the result
 * screen should say and, on failure, whether — and how — retrying makes
 * sense. Kept as a pure function so `CheckInOutFlow`'s branching is testable
 * without rendering anything.
 *
 * The QR is static now — it never expires and is never "used up" — so the
 * only QR-side refusal a client can still see is `QR_NOT_FOUND`, meaning the
 * scanned code doesn't belong to this tenant's location at all (the wrong
 * poster, most likely). That is the one case where re-scanning actually
 * helps; every other refusal (GPS, or a thrown network/server error) just
 * needs a fresh location fix against the same QR.
 */
import { describeError } from '@/lib/errors/describeError'
import { isApiError } from '@/lib/api/errors'
import { describeRefusalReason } from '@/features/attendance/reasonMessages'
import type { AttendanceActionResponse } from '@/lib/api/types'

const QR_REASONS = new Set(['QR_NOT_FOUND'])
const STATE_REASONS = new Set(['ALREADY_CHECKED_IN', 'NOT_CHECKED_IN'])

export type RetryTarget = 'scan' | 'gps' | null

export interface AttendanceOutcome {
  status: 'success' | 'refused' | 'error'
  title: string
  message: string
  retryTarget: RetryTarget
  /** True when this action first found the previous shift still open past
   * the configured cutoff and closed it automatically before doing
   * anything else — worth telling the person, not just acting on silently. */
  autoClosedPreviousSession?: boolean
}

/** `settledResult` is either the resolved `AttendanceActionResponse` (which
 * may itself be a refusal — a 200 is not the same as success) or the thrown
 * error from a rejected mutation. */
export function resolveOutcome(settledResult: AttendanceActionResponse | unknown): AttendanceOutcome {
  if (isAttendanceActionResponse(settledResult)) {
    if (settledResult.success) {
      return {
        status: 'success',
        title: 'Success',
        message: '',
        retryTarget: null,
        autoClosedPreviousSession: settledResult.auto_closed_previous_session,
      }
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
