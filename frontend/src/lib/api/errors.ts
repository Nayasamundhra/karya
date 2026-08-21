/**
 * The frontend's normalized error shape.
 *
 * Every failure that can reach a component — network failure, timeout,
 * cancellation, or any HTTP error status — is normalized into one
 * `ApiError` so UI code never branches on `fetch` internals or on the
 * backend's raw JSON shape. See `docs/error-handling.md` for the full
 * status → experience table this implements.
 */

/** One sanitised Pydantic validation issue, exactly as the backend emits it. */
export interface ValidationIssue {
  /** e.g. "string_too_short", "value_error", "missing" */
  type: string
  /** Field path, e.g. ["body", "password"] — may contain array indices. */
  loc: Array<string | number>
  /** Human-readable rule description. Never the submitted value. */
  msg: string
}

export type ApiErrorKind =
  /** `fetch` itself rejected — DNS, TCP, TLS, CORS preflight, offline. */
  | 'network'
  /** The client's own timeout fired before a response arrived. */
  | 'timeout'
  /** The request was aborted deliberately (route change, new search, unmount). */
  | 'cancelled'
  /** 401 — not authenticated, or the session could not be refreshed. */
  | 'unauthorized'
  /** 403 — authenticated, but not permitted. */
  | 'forbidden'
  /** 404 */
  | 'not_found'
  /** 409 — e.g. duplicate email, last-admin protection. */
  | 'conflict'
  /** 422 — malformed or smuggled fields. `validationErrors` is populated. */
  | 'validation'
  /** 429 — `retryAfterSeconds` is populated when the header was present. */
  | 'rate_limited'
  /** 500 */
  | 'server'
  /** 503 — currently only `/ready`, kept for completeness. */
  | 'unavailable'
  /** Any other status code, or a response body that didn't parse. */
  | 'unknown'

export interface ApiErrorInit {
  kind: ApiErrorKind
  message: string
  status?: number | null
  requestId?: string | null
  retryAfterSeconds?: number | null
  validationErrors?: ValidationIssue[] | null
  cause?: unknown
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly requestId: string | null
  readonly retryAfterSeconds: number | null
  readonly validationErrors: ValidationIssue[] | null

  constructor(init: ApiErrorInit) {
    super(init.message, { cause: init.cause })
    this.name = 'ApiError'
    this.kind = init.kind
    this.status = init.status ?? null
    this.requestId = init.requestId ?? null
    this.retryAfterSeconds = init.retryAfterSeconds ?? null
    this.validationErrors = init.validationErrors ?? null
  }

  /** Whether retrying the exact same request might succeed with no other change. */
  get isRetryable(): boolean {
    return this.kind === 'network' || this.kind === 'timeout' || this.kind === 'server'
  }
}

function safeIssues(detail: unknown): ValidationIssue[] | null {
  if (!Array.isArray(detail)) return null
  const issues: ValidationIssue[] = []
  for (const entry of detail) {
    if (
      entry &&
      typeof entry === 'object' &&
      'type' in entry &&
      'loc' in entry &&
      'msg' in entry
    ) {
      issues.push(entry as ValidationIssue)
    }
  }
  return issues.length > 0 ? issues : null
}

function kindForStatus(status: number): ApiErrorKind {
  switch (status) {
    case 401:
      return 'unauthorized'
    case 403:
      return 'forbidden'
    case 404:
      return 'not_found'
    case 409:
      return 'conflict'
    case 422:
      return 'validation'
    case 429:
      return 'rate_limited'
    case 503:
      return 'unavailable'
    default:
      return status >= 500 ? 'server' : 'unknown'
  }
}

/**
 * Build an `ApiError` from a `Response` whose body has already been read as
 * JSON (or `null` if it wasn't JSON / had no body). Karya's backend answers
 * every error as `{"detail": ...}` — a string for most statuses, a
 * sanitised issue list for 422 — so that's the only shape this understands;
 * anything else falls back to a generic message rather than guessing.
 */
export function apiErrorFromResponse(response: Response, body: unknown): ApiError {
  const requestId = response.headers.get('X-Request-ID')
  const kind = kindForStatus(response.status)
  const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail: unknown }).detail : undefined

  const retryAfterHeader = response.headers.get('Retry-After')
  const retryAfterSeconds = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : null

  if (kind === 'validation') {
    return new ApiError({
      kind,
      message: 'The submitted data was rejected.',
      status: response.status,
      requestId,
      validationErrors: safeIssues(detail),
    })
  }

  const message = typeof detail === 'string' ? detail : `Request failed with status ${response.status}`
  return new ApiError({
    kind,
    message,
    status: response.status,
    requestId,
    retryAfterSeconds: Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : null,
  })
}

export function networkApiError(cause: unknown): ApiError {
  return new ApiError({
    kind: 'network',
    message: 'Could not reach the Karya server.',
    cause,
  })
}

export function timeoutApiError(): ApiError {
  return new ApiError({ kind: 'timeout', message: 'The request took too long.' })
}

export function cancelledApiError(): ApiError {
  return new ApiError({ kind: 'cancelled', message: 'The request was cancelled.' })
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}
