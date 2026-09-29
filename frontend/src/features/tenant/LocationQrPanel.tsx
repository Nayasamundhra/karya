/**
 * The tenant's one static QR code: printed or displayed once, scanned by
 * every employee's phone to check in and out from here on. Encodes exactly
 * `{"qr_token": "..."}` — the same shape `qrPayload.ts` expects on the
 * scanning side — nothing else; it identifies this location, and proves
 * nothing about proximity on its own (GPS does that).
 *
 * Regenerating is the only lever against a leaked or over-shared code now
 * that nothing here expires on its own: the old image on screen becomes
 * wrong the instant this succeeds, which is exactly why it asks first.
 */
import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { Download, RotateCw } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog'
import { useRegenerateQrToken } from '@/features/tenant/useLocationMutations'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export function LocationQrPanel({ qrToken, locationName }: { qrToken: string; locationName: string }) {
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const regenerate = useRegenerateQrToken()

  useEffect(() => {
    let cancelled = false
    const payload = JSON.stringify({ qr_token: qrToken })
    QRCode.toDataURL(payload, { width: 480, margin: 2, color: { dark: '#3730a3', light: '#ffffff' } })
      .then((dataUrl) => {
        if (!cancelled) setQrDataUrl(dataUrl)
      })
      .catch(() => {
        // Rendering failure (should not happen for a well-formed payload) —
        // leave whatever was already on screen rather than blanking it.
      })
    return () => {
      cancelled = true
    }
  }, [qrToken])

  async function handleRegenerate() {
    try {
      await regenerate.mutateAsync()
      toast.success('QR code regenerated', 'The previous printed code no longer works.')
    } catch (err) {
      toast.error('Could not regenerate the QR code', describeError(err).message)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Attendance QR code</CardTitle>
        <CardDescription>
          Print this and put it up at {locationName || 'the office'}. Every employee scans the same code, every
          time — it never expires on its own.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
        <div className="flex size-48 shrink-0 items-center justify-center rounded-lg border border-border bg-white p-3">
          {qrDataUrl ? (
            <img src={qrDataUrl} alt={`Attendance QR code for ${locationName || 'this location'}`} className="size-full object-contain" />
          ) : (
            <div className="size-full animate-pulse rounded bg-surface-sunken" aria-hidden="true" />
          )}
        </div>

        <div className="flex flex-1 flex-col gap-2">
          <Button
            variant="secondary"
            className="w-fit"
            disabled={!qrDataUrl}
            onClick={() => {
              if (!qrDataUrl) return
              const link = document.createElement('a')
              link.href = qrDataUrl
              link.download = 'karya-attendance-qr.png'
              link.click()
            }}
          >
            <Download className="size-4" aria-hidden="true" />
            Download
          </Button>

          <Button
            variant="ghost"
            className="w-fit text-danger-600 hover:text-danger-700"
            onClick={() => setConfirmOpen(true)}
          >
            <RotateCw className="size-4" aria-hidden="true" />
            Regenerate code
          </Button>
          <p className="text-xs text-foreground-muted">
            Regenerating immediately invalidates the code above — reprint before anyone tries to scan the old one.
          </p>
        </div>
      </CardContent>

      <ConfirmationDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Regenerate the attendance QR code?"
        description="The current printed code will stop working immediately. Only do this if it's been lost, damaged, or shared somewhere it shouldn't have been."
        confirmLabel="Regenerate"
        confirmVariant="destructive"
        onConfirm={handleRegenerate}
      />
    </Card>
  )
}
