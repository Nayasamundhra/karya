import { useLocation } from '@/features/tenant/useLocation'
import { useDisplayTokens } from '@/features/display/useDisplayTokens'
import { useUsersList } from '@/features/users/admin/useUsersList'

export interface SetupStep {
  id: 'location' | 'display' | 'employees'
  label: string
  done: boolean
  to: string
  cta: string
}

export interface SetupStatus {
  /** True once every hook below has returned (success or error) — the
   * checklist shouldn't flash "incomplete" for steps still loading. */
  isLoading: boolean
  steps: SetupStep[]
  /** Organization creation and email verification are conditions of even
   * reaching an authenticated screen, so they are always "done" here —
   * see `SetupChecklistPage` for why they still render as ticked items. */
  isComplete: boolean
}

/**
 * Derives the PRD §6 setup checklist ("configure location", "set up a
 * display", "add employees") from data the app already fetches elsewhere —
 * there is no dedicated backend "onboarding status" endpoint, and none is
 * needed: each step's completion is exactly what its own feature page
 * already queries for.
 */
export function useSetupStatus(): SetupStatus {
  const location = useLocation()
  const displays = useDisplayTokens()
  // One row is enough to know whether *any* employee exists; the tenant's
  // own onboarding admin (`ADMIN-1`) is always present, so "done" means more
  // than that one row.
  const users = useUsersList({ pageSize: 2 })

  const isLoading = location.isLoading || displays.isLoading || users.isLoading

  const steps: SetupStep[] = [
    {
      id: 'location',
      label: 'Configure attendance location',
      done: Boolean(location.data),
      to: '/admin/organization',
      cta: 'Set up location',
    },
    {
      id: 'display',
      label: 'Set up an attendance display',
      done: Boolean(displays.data && displays.data.items.length > 0),
      to: '/admin/organization',
      cta: 'Create a display',
    },
    {
      id: 'employees',
      label: 'Add employees',
      done: Boolean(users.data && users.data.pagination.total > 1),
      to: '/admin/users',
      cta: 'Manage employees',
    },
  ]

  return { isLoading, steps, isComplete: steps.every((step) => step.done) }
}
