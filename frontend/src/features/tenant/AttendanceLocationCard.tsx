/**
 * The tenant's attendance location: create it once, edit it in place.
 *
 * "Use my current location" only ever fills the latitude/longitude inputs
 * with a raw GPS reading for the admin to review and submit — it is a data
 * entry convenience, not a presence decision. Nothing here computes a
 * distance or a verdict; that stays exclusively the backend's job (§7).
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { Crosshair } from 'lucide-react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Input } from '@/components/ui/Input'
import { Skeleton } from '@/components/ui/Skeleton'
import {
  attendanceLocationSchema,
  type AttendanceLocationFormValues,
} from '@/features/tenant/locationSchema'
import { useCreateLocation, useUpdateLocation } from '@/features/tenant/useLocationMutations'
import { useLocation } from '@/features/tenant/useLocation'
import { GEOLOCATION_ERROR_MESSAGES, useGeolocation } from '@/hooks/useGeolocation'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export function AttendanceLocationCard() {
  const { data: location, isLoading, isError, error, refetch } = useLocation()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Attendance location</CardTitle>
        <CardDescription>
          Employees must be within this radius, and scan the office display's QR code, to check in
          or out.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-11 w-full" />}
        {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
        {!isLoading && !isError && (
          <LocationForm existing={location ?? null} />
        )}
      </CardContent>
    </Card>
  )
}

interface ExistingLocation {
  name: string
  description: string | null
  latitude: number
  longitude: number
  geofence_radius_meters: number
}

function LocationForm({ existing }: { existing: ExistingLocation | null }) {
  const createLocation = useCreateLocation()
  const updateLocation = useUpdateLocation()
  const geolocation = useGeolocation()
  const mutation = existing ? updateLocation : createLocation

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isDirty },
  } = useForm<AttendanceLocationFormValues>({
    resolver: zodResolver(attendanceLocationSchema),
    defaultValues: existing
      ? {
          name: existing.name,
          description: existing.description ?? '',
          latitude: existing.latitude,
          longitude: existing.longitude,
          geofenceRadiusMeters: existing.geofence_radius_meters,
        }
      : { name: '', description: '', latitude: 0, longitude: 0, geofenceRadiusMeters: 150 },
  })

  // Fill the coordinate fields the instant a fix arrives — this form has no
  // other use for `useGeolocation`'s loading/permission state beyond the one
  // button below, so there is nothing else to react to here.
  useEffect(() => {
    if (!geolocation.coordinates) return
    setValue('latitude', geolocation.coordinates.latitude, { shouldDirty: true })
    setValue('longitude', geolocation.coordinates.longitude, { shouldDirty: true })
  }, [geolocation.coordinates, setValue])

  // Same pattern as `TenantSettingsCard`: re-sync from the server once it has
  // something to sync from, but never fight a user who is mid-edit. This is
  // what turns a just-created location into a clean, non-dirty "edit" form
  // on the very next render, with no separate create-vs-edit remount needed.
  useEffect(() => {
    if (existing && !isDirty) {
      reset({
        name: existing.name,
        description: existing.description ?? '',
        latitude: existing.latitude,
        longitude: existing.longitude,
        geofenceRadiusMeters: existing.geofence_radius_meters,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing, isDirty])

  async function onSubmit(values: AttendanceLocationFormValues) {
    const payload = {
      name: values.name,
      // "" means "no description" — sent through as-is; the backend's own
      // `trim_or_none` treats an empty string the same as omitting it.
      description: values.description,
      latitude: values.latitude,
      longitude: values.longitude,
      geofence_radius_meters: values.geofenceRadiusMeters,
    }
    try {
      await mutation.mutateAsync(payload)
      toast.success(existing ? 'Attendance location updated' : 'Attendance location created')
    } catch (err) {
      toast.error('Could not save attendance location', describeError(err).message)
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {!existing && (
        <Alert variant="info" title="Not set up yet">
          Employees can't check in or out until an attendance location exists.
        </Alert>
      )}

      <Input label="Location name" placeholder="Head Office" error={errors.name?.message} {...register('name')} />

      <Input
        label="Description (optional)"
        placeholder="3rd floor, Brigade Towers"
        error={errors.description?.message}
        {...register('description')}
      />

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Latitude"
          type="number"
          step="any"
          error={errors.latitude?.message}
          {...register('latitude', { valueAsNumber: true })}
        />
        <Input
          label="Longitude"
          type="number"
          step="any"
          error={errors.longitude?.message}
          {...register('longitude', { valueAsNumber: true })}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="w-fit"
          isLoading={geolocation.isLoading}
          onClick={() => geolocation.request()}
        >
          <Crosshair className="size-4" aria-hidden="true" />
          Use this device's current location
        </Button>
        {geolocation.error && (
          <p className="text-xs text-danger-600">{GEOLOCATION_ERROR_MESSAGES[geolocation.error]}</p>
        )}
      </div>

      <Input
        label="Geofence radius (meters)"
        type="number"
        error={errors.geofenceRadiusMeters?.message}
        {...register('geofenceRadiusMeters', { valueAsNumber: true })}
      />

      <div>
        <Button type="submit" isLoading={mutation.isPending} disabled={existing ? !isDirty : false}>
          {mutation.isPending ? 'Saving…' : existing ? 'Save changes' : 'Create attendance location'}
        </Button>
      </div>
    </form>
  )
}
