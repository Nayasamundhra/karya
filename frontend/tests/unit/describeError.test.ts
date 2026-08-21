import { describe, expect, it } from 'vitest'

import { ApiError, apiErrorFromResponse, networkApiError, timeoutApiError } from '@/lib/api/errors'
import { describeError } from '@/lib/errors/describeError'

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

describe('apiErrorFromResponse', () => {
  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [409, 'conflict'],
    [429, 'rate_limited'],
    [500, 'server'],
    [503, 'unavailable'],
  ] as const)('maps HTTP %i to kind %s', async (status, kind) => {
    const response = jsonResponse(status, { detail: 'something' })
    const error = apiErrorFromResponse(response, { detail: 'something' })
    expect(error.kind).toBe(kind)
    expect(error.status).toBe(status)
  })

  it('extracts sanitised validation issues from a 422 without ever seeing a submitted value', () => {
    const body = { detail: [{ type: 'string_too_short', loc: ['body', 'password'], msg: 'Too short' }] }
    const error = apiErrorFromResponse(jsonResponse(422, body), body)
    expect(error.kind).toBe('validation')
    expect(error.validationErrors).toEqual([{ type: 'string_too_short', loc: ['body', 'password'], msg: 'Too short' }])
  })

  it('reads Retry-After for a 429', () => {
    const body = { detail: 'Too many requests' }
    const error = apiErrorFromResponse(jsonResponse(429, body, { 'Retry-After': '17' }), body)
    expect(error.retryAfterSeconds).toBe(17)
  })

  it('carries the X-Request-ID header through for support/debug display', () => {
    const body = { detail: 'Internal server error' }
    const error = apiErrorFromResponse(jsonResponse(500, body, { 'X-Request-ID': 'abc123' }), body)
    expect(error.requestId).toBe('abc123')
  })
})

describe('describeError', () => {
  it('gives a retryable, generic message for a network failure', () => {
    const description = describeError(networkApiError(new Error('boom')))
    expect(description.retryable).toBe(true)
    expect(description.title).toMatch(/reach karya/i)
  })

  it('gives a non-retryable message for a timeout that is distinguishable from a hard network failure', () => {
    const description = describeError(timeoutApiError())
    expect(description.title).not.toMatch(/reach karya/i)
  })

  it('never suggests retrying a 403 (retrying does not change who you are)', () => {
    const description = describeError(new ApiError({ kind: 'forbidden', message: "You don't have permission" }))
    expect(description.retryable).toBe(false)
  })

  it('never suggests retrying a 422 (the input needs to change, not the request)', () => {
    const description = describeError(new ApiError({ kind: 'validation', message: 'bad input' }))
    expect(description.retryable).toBe(false)
  })

  it('turns an unrecognised thrown value into a safe generic message rather than crashing', () => {
    const description = describeError('a raw string was thrown, not an Error')
    expect(description.title).toBe('Something went wrong')
  })
})
