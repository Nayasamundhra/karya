/**
 * Copy for a *business refusal* — `AttendanceActionResponse.reason` on a
 * `success: false` response (HTTP 200). This is a different axis from
 * `describeError`/`ApiError`: those cover requests that could not be
 * processed at all (network, 401, 429, 5xx); this covers requests that were
 * fully processed and refused, which is Karya's normal way of saying "no,
 * and here is why" (CLAUDE.md, backend README §8d).
 *
 * `reason` is typed as a plain `string` on the wire (it is the union of two
 * backend enums — presence `FailureReason` and attendance's own
 * `ALREADY_CHECKED_IN`/`NOT_CHECKED_IN` — deliberately not restated as one
 * type there), so this map's key type stays `string` and anything unmapped
 * falls back to a generic message rather than rendering `undefined`.
 */
const REASON_MESSAGES: Record<string, string> = {
  QR_EXPIRED: 'This QR code has expired. Please scan the current code.',
  QR_ALREADY_USED: 'This QR code has already been used. Please scan the current code.',
  // QR_TENANT_MISMATCH and QR_LOCATION_MISMATCH never reach the client — the
  // backend collapses both to QR_NOT_FOUND before responding (see
  // `app.services.presence.results.CLIENT_SAFE_REASON`) — so one message
  // covers "not found" and "wrong tenant" identically, by design.
  QR_NOT_FOUND: "This QR code isn't valid. Please scan the current code.",
  QR_REVOKED: 'This QR code is no longer active. Please scan the current code.',
  QR_NONCE_MISMATCH: "This QR code isn't valid. Please scan the current code.",
  OUTSIDE_GEOFENCE: 'You appear to be outside the office area.',
  GPS_ACCURACY_TOO_LOW:
    "Your location isn't accurate enough. Please move to an area with a clearer GPS signal and try again.",
  GPS_INVALID: 'Your location could not be determined. Please try again.',
  NO_ACTIVE_ATTENDANCE_LOCATION: "Attendance isn't set up yet. Contact your administrator.",
  ALREADY_CHECKED_IN: 'You are already checked in.',
  NOT_CHECKED_IN: 'You are not currently checked in.',
}

const DEFAULT_MESSAGE = 'Attendance could not be verified. Please try again.'

/** `reason` is `null`/`undefined` for a successful attempt — callers only
 * need this for the `success: false` branch. */
export function describeRefusalReason(reason: string | null | undefined): string {
  if (!reason) return DEFAULT_MESSAGE
  return REASON_MESSAGES[reason] ?? DEFAULT_MESSAGE
}
