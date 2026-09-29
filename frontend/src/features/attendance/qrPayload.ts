/**
 * Parses the text decoded off the office QR into the one field the backend
 * accepts. The QR is now **static** — printed or displayed once per
 * attendance location, never rotated — and encodes exactly
 * `{"qr_token": "..."}` as JSON, nothing else.
 *
 * This is a **format** check only, not a trust boundary: a well-formed
 * `{qr_token}` that doesn't resolve to this tenant's location is still
 * rejected by the backend on submission. This module exists solely to turn
 * "not even shaped like a Karya QR code" into a clear, immediate message
 * instead of a confusing 422 round-trip.
 */
import { z } from 'zod'

const qrPayloadSchema = z.object({
  qr_token: z.string().uuid(),
})

export type QrPayload = z.infer<typeof qrPayloadSchema>

export type QrParseResult = { ok: true; payload: QrPayload } | { ok: false }

/** Never throws — a scanned code that isn't valid JSON, or doesn't match the
 * shape, is just `{ ok: false }` for the caller to show "invalid QR" for. */
export function parseQrPayload(text: string): QrParseResult {
  let json: unknown
  try {
    json = JSON.parse(text)
  } catch {
    return { ok: false }
  }

  const result = qrPayloadSchema.safeParse(json)
  return result.success ? { ok: true, payload: result.data } : { ok: false }
}
