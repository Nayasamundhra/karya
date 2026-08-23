/**
 * Parses the text decoded off the office QR into the two fields the backend
 * accepts. Per `backend/README.md` §"Presence verification protocol", the
 * display encodes exactly `{"challenge_id": "...", "nonce": "..."}` as JSON
 * — nothing else.
 *
 * This is a **format** check only, not a trust boundary: a well-formed
 * `{challenge_id, nonce}` pair that is expired, already used, or from
 * another tenant is still rejected — by the backend, on submission (§4: "do
 * not trust anything inside the QR"). This module exists solely to turn
 * "not even shaped like a Karya QR code" into a clear, immediate message
 * instead of a confusing 422 round-trip.
 */
import { z } from 'zod'

const qrPayloadSchema = z.object({
  challenge_id: z.string().uuid(),
  nonce: z.string().min(1),
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
