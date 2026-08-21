/**
 * The single place backend error shapes turn into user-facing copy — see
 * `docs/error-handling.md` for the full status table this implements. A
 * component should call `describeError(error)` and render the result; it
 * should never inspect `ApiError.status` or `.kind` itself to decide what to
 * say, so the copy stays consistent everywhere and can be revised in one
 * place.
 */
import { type ApiError, isApiError } from '@/lib/api/errors'

export interface ErrorDescription {
  title: string
  message: string
  /** Whether offering a "Try again" action makes sense for this failure. */
  retryable: boolean
  /** A support/debug detail — the request id, shown only where useful (see §16). */
  requestId: string | null
}

const KIND_COPY: Record<ApiError['kind'], { title: string; message: string; retryable: boolean }> = {
  network: {
    title: "Can't reach Karya",
    message: 'Check your connection and try again.',
    retryable: true,
  },
  timeout: {
    title: 'That took too long',
    message: 'The request timed out. Try again.',
    retryable: true,
  },
  cancelled: {
    title: 'Cancelled',
    message: 'The request was cancelled.',
    retryable: false,
  },
  unauthorized: {
    title: 'Your session has expired',
    message: 'Sign in again to continue.',
    retryable: false,
  },
  forbidden: {
    title: "You don't have permission",
    message: 'This action needs a different role. Contact your administrator if this seems wrong.',
    retryable: false,
  },
  not_found: {
    title: 'Not found',
    message: "That item doesn't exist, or you don't have access to it.",
    retryable: false,
  },
  conflict: {
    title: "That didn't go through",
    message: 'This conflicts with the current state — refresh and try again.',
    retryable: false,
  },
  validation: {
    title: 'Check the form',
    message: 'Some fields need to be fixed before this can be submitted.',
    retryable: false,
  },
  rate_limited: {
    title: 'Too many attempts',
    message: 'Please wait a moment before trying again.',
    retryable: true,
  },
  server: {
    title: 'Something went wrong',
    message: 'This is on us, not you. Try again in a moment.',
    retryable: true,
  },
  unavailable: {
    title: 'Service temporarily unavailable',
    message: 'Karya is temporarily unavailable. Try again shortly.',
    retryable: true,
  },
  unknown: {
    title: 'Something went wrong',
    message: 'An unexpected error occurred.',
    retryable: true,
  },
}

export function describeError(error: unknown): ErrorDescription {
  if (isApiError(error)) {
    const base = KIND_COPY[error.kind]
    const message =
      error.kind === 'rate_limited' && error.retryAfterSeconds
        ? `Please wait about ${error.retryAfterSeconds}s before trying again.`
        : // 401/403/404/409 messages from the backend are already
          // deliberately generic and safe to show verbatim (Karya's
          // anti-enumeration design guarantees this — see backend
          // README §8a/§8d); everything else uses the fixed copy above
          // rather than surfacing raw backend text.
          error.kind === 'conflict' || error.kind === 'forbidden' || error.kind === 'not_found'
          ? error.message || base.message
          : base.message
    return { title: base.title, message, retryable: base.retryable, requestId: error.requestId }
  }

  return { title: 'Something went wrong', message: 'An unexpected error occurred.', retryable: true, requestId: null }
}
