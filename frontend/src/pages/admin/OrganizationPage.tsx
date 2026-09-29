import { Building2 } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { AttendanceLocationCard } from '@/features/tenant/AttendanceLocationCard'
import { TenantSettingsCard } from '@/features/tenant/TenantSettingsCard'
import { SetupProgressStrip } from '@/features/onboarding/SetupProgressStrip'

const TAB_VALUES = ['details', 'location'] as const
type TabValue = (typeof TAB_VALUES)[number]

function isTabValue(value: string | null): value is TabValue {
  return TAB_VALUES.includes(value as TabValue)
}

/**
 * "How is this tenant configured?" — organization details and the
 * attendance location (which now carries its own static QR panel — see
 * `AttendanceLocationCard`) live here as tabs rather than one long page.
 *
 * TENANT_ADMIN only (see `router.tsx`): renaming the tenant, moving the
 * attendance geofence and regenerating the location's QR are all
 * admin-level decisions. A "Displays" tab existed here through Phase 11 for
 * kiosk-credential management; it was removed along with the kiosk
 * mechanism itself once the QR became a static, printed code with nothing
 * left to provision.
 */
export default function OrganizationPage() {
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const initialTab: TabValue = isTabValue(requestedTab) ? requestedTab : 'details'

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-admin-50 text-admin-700">
          <Building2 className="size-5" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-xl font-semibold text-foreground">Organization</h1>
          <p className="text-sm text-foreground-muted">Settings and attendance location.</p>
        </div>
      </div>

      <SetupProgressStrip />

      <Tabs defaultValue={initialTab}>
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="location">Attendance location</TabsTrigger>
        </TabsList>

        <TabsContent value="details">
          <TenantSettingsCard />
        </TabsContent>

        <TabsContent value="location">
          <AttendanceLocationCard />
        </TabsContent>
      </Tabs>
    </div>
  )
}
