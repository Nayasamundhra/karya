import { describe, expect, it } from 'vitest'

import { parseQrPayload } from '@/features/attendance/qrPayload'

describe('parseQrPayload', () => {
  it('accepts the documented {challenge_id, nonce} shape', () => {
    const result = parseQrPayload(
      JSON.stringify({ challenge_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6', nonce: 'a-real-nonce' }),
    )
    expect(result).toEqual({
      ok: true,
      payload: { challenge_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6', nonce: 'a-real-nonce' },
    })
  })

  it('rejects text that is not JSON at all — e.g. a QR meant for a different app', () => {
    expect(parseQrPayload('https://example.com/not-karya')).toEqual({ ok: false })
  })

  it('rejects JSON missing a field', () => {
    expect(parseQrPayload(JSON.stringify({ challenge_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6' }))).toEqual({
      ok: false,
    })
  })

  it('rejects a challenge_id that is not a UUID', () => {
    expect(parseQrPayload(JSON.stringify({ challenge_id: 'not-a-uuid', nonce: 'x' }))).toEqual({ ok: false })
  })

  it('rejects an empty nonce', () => {
    expect(
      parseQrPayload(JSON.stringify({ challenge_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6', nonce: '' })),
    ).toEqual({ ok: false })
  })

  it('never throws on malformed input', () => {
    expect(() => parseQrPayload('{{{not json')).not.toThrow()
    expect(() => parseQrPayload('')).not.toThrow()
  })
})
