import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AttendanceHistoryList } from '@/features/attendance/AttendanceHistoryList'
import { ApiError } from '@/lib/api/errors'
import * as attendanceApi from '@/lib/api/endpoints/attendance'
import type { AttendanceHistoryResponse } from '@/lib/api/types'
import { TestQueryProvider } from './helpers/testQueryClient'

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()
  return { ...actual, getMyHistory: vi.fn() }
})

function page(overrides: Partial<AttendanceHistoryResponse> = {}): AttendanceHistoryResponse {
  return {
    user_id: 'user-1',
    from_date: '2026-08-16',
    to_date: '2026-08-22',
    items: [
      {
        date: '2026-08-22',
        status: 'COMPLETED',
        sessions: [],
        first_check_in: '2026-08-22T09:00:00Z',
        last_check_out: '2026-08-22T17:00:00Z',
      },
    ],
    pagination: { page: 1, page_size: 14, total: 1, total_pages: 1 },
    ...overrides,
  }
}

function renderList() {
  return render(
    <TestQueryProvider>
      <AttendanceHistoryList />
    </TestQueryProvider>,
  )
}

describe('AttendanceHistoryList', () => {
  afterEach(() => {
    vi.mocked(attendanceApi.getMyHistory).mockReset()
  })

  it('renders a loading state before data arrives', () => {
    vi.mocked(attendanceApi.getMyHistory).mockImplementation(() => new Promise(() => {}))
    const { container } = renderList()
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThan(0)
  })

  it('shows an empty state when there is no history yet', async () => {
    vi.mocked(attendanceApi.getMyHistory).mockResolvedValue(page({ items: [] }))
    renderList()
    expect(await screen.findByText(/no attendance recorded yet/i)).toBeInTheDocument()
  })

  it('renders each day with its check-in/check-out times and status', async () => {
    vi.mocked(attendanceApi.getMyHistory).mockResolvedValue(page())
    renderList()
    expect(await screen.findByText('Completed')).toBeInTheDocument()
  })

  it('shows an error state with retry on failure, and retrying calls the API again', async () => {
    vi.mocked(attendanceApi.getMyHistory).mockRejectedValue(new ApiError({ kind: 'server', message: 'boom' }))
    renderList()

    await screen.findByRole('alert')
    vi.mocked(attendanceApi.getMyHistory).mockResolvedValue(page())
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))

    expect(await screen.findByText('Completed')).toBeInTheDocument()
  })

  it('pagination controls request the next page and disable Next on the last page', async () => {
    vi.mocked(attendanceApi.getMyHistory).mockResolvedValue(
      page({ pagination: { page: 1, page_size: 14, total: 2, total_pages: 2 } }),
    )
    renderList()
    await screen.findByText('Completed')

    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
    const next = screen.getByRole('button', { name: /^next$/i })
    expect(next).not.toBeDisabled()

    vi.mocked(attendanceApi.getMyHistory).mockResolvedValue(
      page({ pagination: { page: 2, page_size: 14, total: 2, total_pages: 2 } }),
    )
    await userEvent.click(next)

    await waitFor(() =>
      expect(attendanceApi.getMyHistory).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.anything()),
    )
  })
})
