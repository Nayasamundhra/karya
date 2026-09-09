import { Building2 } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { AttendanceLocationCard } from '@/features/tenant/AttendanceLocationCard'
import { TenantSettingsCard } from '@/features/tenant/TenantSettingsCard'
import { DisplayTokensCard } from '@/features/display/DisplayTokensCard'
import { SetupProgressStrip } from '@/features/onboarding/SetupProgressStrip'
import { useAuth } from '@/features/auth/useAuth'

const TAB_VALUES = ['details', 'location', 'displays'] as const
type TabValue = (typeof TAB_VALUES)[number]

function isTabValue(value: string | null): value is TabValue {
  return TAB_VALUES.includes(value as TabValue)
}

/**
 * "How is this tenant configured?" (§24) — the three subsections a tenant
 * admin needs (organization details, the attendance location, the office
 * displays) live here as tabs rather than one long page, matching §19's
 * "logically separated" requirement. Each tab is the same feature-level
 * card `ProfilePage` used to render inline; nothing here duplicates their
 * data-fetching or mutation logic.
 *
 * MANAGER also reaches this route (see `router.tsx`) because the backend's
 * `QR_ISSUER_ROLES` already lets a manager create/list/revoke display
 * tokens — but renaming the tenant or moving the attendance geofence are
 * genuinely admin-level decisions, so a manager sees the Displays content
 * directly, with no tab list and no path to the other two.
 */
export default function OrganizationPage() {
  const { user } = useAuth()
  const isTenantAdmin = user?.role === 'TENANT_ADMIN'
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  // A "Generate display QR" shortcut elsewhere (e.g. `TeamHeadline`) can
  // deep-link straight to the Displays tab via `?tab=displays`, instead of
  // landing an admin on Details and making them click again.
  const initialTab: TabValue = isTabValue(requestedTab) ? requestedTab : 'details'

  if (!isTenantAdmin) {
    return (
      <div className="flex max-w-3xl flex-col gap-6">
        <h1 className="text-xl font-semibold text-foreground">Displays</h1>
        <DisplayTokensCard />
      </div>
    )
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-admin-50 text-admin-700">
          <Building2 className="size-5" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-xl font-semibold text-foreground">Organization</h1>
          <p className="text-sm text-foreground-muted">Settings, attendance location, and office displays.</p>
        </div>
      </div>

      <SetupProgressStrip />

      <Tabs defaultValue={initialTab}>
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="location">Attendance location</TabsTrigger>
          <TabsTrigger value="displays">Displays</TabsTrigger>
        </TabsList>

        <TabsContent value="details">
          <TenantSettingsCard />
        </TabsContent>

        <TabsContent value="location">
          <AttendanceLocationCard />
        </TabsContent>

        <TabsContent value="displays">
          <DisplayTokensCard />
        </TabsContent>
      </Tabs>
    </div>
  )
}
