import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDebouncedValue } from '@/hooks/useDebouncedValue'

describe('useDebouncedValue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('only reflects the latest value after the delay, not every intermediate keystroke', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 300), {
      initialProps: { value: 'a' },
    })

    expect(result.current).toBe('a')

    rerender({ value: 'ac' })
    act(() => vi.advanceTimersByTime(100))
    rerender({ value: 'acm' })
    act(() => vi.advanceTimersByTime(100))
    rerender({ value: 'acme' })

    // Still the initial value — none of the intermediate keystrokes' timers
    // ran to completion (§10: no request per keystroke).
    expect(result.current).toBe('a')

    act(() => vi.advanceTimersByTime(300))
    expect(result.current).toBe('acme')
  })
})
