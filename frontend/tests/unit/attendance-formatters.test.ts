import { describe, expect, it } from 'vitest'

import { formatHours } from '@/features/attendance/formatters'

describe('formatHours', () => {
  it('formats an exact hour with no minutes', () => {
    expect(formatHours(1)).toBe('1h')
    expect(formatHours(8)).toBe('8h')
  })

  it('formats under an hour as minutes only', () => {
    expect(formatHours(0)).toBe('0m')
    expect(formatHours(0.5)).toBe('30m')
  })

  it('formats hours and minutes together', () => {
    expect(formatHours(1.5)).toBe('1h 30m')
    expect(formatHours(8.5)).toBe('8h 30m')
  })

  it('rounds to the nearest minute', () => {
    expect(formatHours(7.99)).toBe('7h 59m') // 479.4 minutes -> 479
    expect(formatHours(1 + 59.6 / 60)).toBe('2h') // 3596.4s worth of minutes rounds up into the next hour
  })
})
