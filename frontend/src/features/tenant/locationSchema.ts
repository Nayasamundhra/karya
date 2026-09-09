import { z } from 'zod'

import { LOCATION_DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH } from '@/lib/validation/constants'

// Mirrors `backend/app/schemas/attendance_location.py`'s bounds exactly —
// loose guardrails against a fat-fingered value, not a product opinion.
const MIN_RADIUS_METERS = 10
const MAX_RADIUS_METERS = 5_000

// Plain `z.number()`, not `z.coerce.number()`: the inputs below use
// react-hook-form's own `valueAsNumber` to deliver a real number to the
// resolver, so the form's input and output types match exactly — mixing in
// `z.coerce` here makes them diverge (`unknown` in, `number` out) in a way
// that `useForm<AttendanceLocationFormValues>` can't express in one generic.
export const attendanceLocationSchema = z.object({
  name: z.string().trim().min(1, 'Location name is required').max(NAME_MAX_LENGTH),
  // Optional (PRD §7) — an empty string is a valid "no description", same as
  // never having typed one; the backend's own `trim_or_none` makes the same
  // call server-side.
  description: z.string().trim().max(LOCATION_DESCRIPTION_MAX_LENGTH),
  latitude: z.number().min(-90, 'Must be between -90 and 90').max(90, 'Must be between -90 and 90'),
  longitude: z
    .number()
    .min(-180, 'Must be between -180 and 180')
    .max(180, 'Must be between -180 and 180'),
  geofenceRadiusMeters: z
    .number()
    .int('Must be a whole number')
    .min(MIN_RADIUS_METERS, `Must be at least ${MIN_RADIUS_METERS}m`)
    .max(MAX_RADIUS_METERS, `Must be at most ${MAX_RADIUS_METERS}m`),
})

export type AttendanceLocationFormValues = z.infer<typeof attendanceLocationSchema>
