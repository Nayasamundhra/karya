import { act, render } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import jsQR from 'jsqr'

import { QrScanner } from '@/features/attendance/QrScanner'

vi.mock('jsqr', () => ({ default: vi.fn() }))

const startMock = vi.fn().mockResolvedValue(undefined)
const stopMock = vi.fn()

vi.mock('@/hooks/useCameraStream', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useCameraStream')>()
  return {
    ...actual,
    // A real `useRef` (not a plain object) so React's `ref` callback on the
    // rendered `<video>` assigns the actual DOM node here, exactly like the
    // real hook — the test only fakes permission/start/stop, not the ref
    // plumbing.
    useCameraStream: () => {
      const videoRef = useRef<HTMLVideoElement>(null)
      return { permission: 'granted' as const, isLoading: false, error: null, videoRef, start: startMock, stop: stopMock }
    },
  }
})

function markVideoReady(container: HTMLElement) {
  const video = container.querySelector('video')
  if (!video) throw new Error('video element not rendered')
  Object.defineProperty(video, 'readyState', { value: 2, configurable: true })
  Object.defineProperty(video, 'videoWidth', { value: 640, configurable: true })
  Object.defineProperty(video, 'videoHeight', { value: 480, configurable: true })
}

describe('QrScanner', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      drawImage: vi.fn(),
      getImageData: vi.fn().mockReturnValue({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
    }) as unknown as HTMLCanvasElement['getContext']
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.mocked(jsQR).mockReset()
    startMock.mockClear()
    stopMock.mockClear()
  })

  // `start()` resolves asynchronously (a microtask) before the decode loop's
  // effect turns on — flushing it explicitly is what lets fake-timer
  // advances below actually reach a running `setInterval`.
  async function flushCameraStart() {
    await act(async () => {
      await Promise.resolve()
    })
  }

  it('decodes a scanned code exactly once and stops the camera immediately', async () => {
    vi.mocked(jsQR).mockReturnValue({ data: '{"challenge_id":"x","nonce":"y"}' } as ReturnType<typeof jsQR>)
    const onDecode = vi.fn()
    const { container } = render(<QrScanner active onDecode={onDecode} />)
    markVideoReady(container)
    await flushCameraStart()

    act(() => {
      vi.advanceTimersByTime(200)
    })

    expect(onDecode).toHaveBeenCalledTimes(1)
    expect(onDecode).toHaveBeenCalledWith('{"challenge_id":"x","nonce":"y"}')
    expect(stopMock).toHaveBeenCalledTimes(1)
  })

  it('never fires onDecode twice, even if further scan ticks elapse before the parent reacts', async () => {
    vi.mocked(jsQR).mockReturnValue({ data: 'payload' } as ReturnType<typeof jsQR>)
    const onDecode = vi.fn()
    const { container } = render(<QrScanner active onDecode={onDecode} />)
    markVideoReady(container)
    await flushCameraStart()

    act(() => {
      vi.advanceTimersByTime(200)
      vi.advanceTimersByTime(200)
      vi.advanceTimersByTime(200)
    })

    expect(onDecode).toHaveBeenCalledTimes(1)
  })

  it('does not decode every tick when no code is in frame — jsQR is polled, not left unbounded', async () => {
    vi.mocked(jsQR).mockReturnValue(null)
    const onDecode = vi.fn()
    const { container } = render(<QrScanner active onDecode={onDecode} />)
    markVideoReady(container)
    await flushCameraStart()

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(onDecode).not.toHaveBeenCalled()
    // 1000ms / 200ms interval = 5 ticks, not one call per animation frame.
    expect(jsQR).toHaveBeenCalledTimes(5)
  })

  it('renders nothing, and starts nothing, while inactive', () => {
    const { container } = render(<QrScanner active={false} onDecode={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
    expect(startMock).not.toHaveBeenCalled()
  })

  it('stops the camera on unmount, even mid-scan', () => {
    vi.mocked(jsQR).mockReturnValue(null)
    const { unmount } = render(<QrScanner active onDecode={vi.fn()} />)
    unmount()
    expect(stopMock).toHaveBeenCalled()
  })
})
