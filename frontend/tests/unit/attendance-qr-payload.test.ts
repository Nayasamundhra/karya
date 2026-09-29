import { describe, expect, it } from 'vitest'

import { parseQrPayload } from '@/features/attendance/qrPayload'

describe('parseQrPayload', () => {
  it('accepts the documented {qr_token} shape', () => {
    const result = parseQrPayload(JSON.stringify({ qr_token: '3fa85f64-5717-4562-b3fc-2c963f66afa6' }))
    expect(result).toEqual({
      ok: true,
      payload: { qr_token: '3fa85f64-5717-4562-b3fc-2c963f66afa6' },
    })
  })

  it('rejects text that is not JSON at all — e.g. a QR meant for a different app', () => {
    expect(parseQrPayload('https://example.com/not-karya')).toEqual({ ok: false })
  })

  it('rejects JSON missing the field', () => {
    expect(parseQrPayload(JSON.stringify({}))).toEqual({ ok: false })
  })

  it('rejects a qr_token that is not a UUID', () => {
    expect(parseQrPayload(JSON.stringify({ qr_token: 'not-a-uuid' }))).toEqual({ ok: false })
  })

  it('never throws on malformed input', () => {
    expect(() => parseQrPayload('{{{not json')).not.toThrow()
    expect(() => parseQrPayload('')).not.toThrow()
  })
})
