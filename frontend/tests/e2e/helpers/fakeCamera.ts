import QRCode from 'qrcode'
import type { Page } from '@playwright/test'

/**
 * Replaces `getUserMedia` with a synthetic video stream showing a real,
 * scannable QR code — so the app's actual `jsQR` decode loop
 * (`src/features/attendance/QrScanner.tsx`) runs completely unmodified
 * against real pixel data, with no physical camera required (§20: "do not
 * require a physical camera or GPS device for automated tests"). Only the
 * *camera hardware* is faked; nothing about how Karya scans or verifies a
 * code is.
 */
export async function stubCameraWithQrPayload(page: Page, payload: unknown): Promise<void> {
  const dataUrl = await QRCode.toDataURL(JSON.stringify(payload), { margin: 1, width: 400 })
  await page.addInitScript((qrDataUrl: string) => {
    navigator.mediaDevices.getUserMedia = async () => {
      const img = new Image()
      img.src = qrDataUrl
      await img.decode()
      const canvas = document.createElement('canvas')
      canvas.width = 480
      canvas.height = 480
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.fillStyle = 'white'
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.drawImage(img, 40, 40, 400, 400)
      }
      // captureStream is a real MediaStream — the app's `<video>` element and
      // canvas-sampling decode loop treat it exactly like a live camera.
      return (canvas as HTMLCanvasElement & { captureStream: (fps?: number) => MediaStream }).captureStream(5)
    }
  }, dataUrl)
}

/** No usable camera at all — the "camera unavailable" path (§4/§20), also
 * with no real hardware involved. */
export async function stubCameraUnavailable(page: Page): Promise<void> {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => {
      return Promise.reject(new DOMException('No camera found', 'NotFoundError'))
    }
  })
}
