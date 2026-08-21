import { UserCog } from 'lucide-react'

import { ComingSoon } from '@/components/feedback/ComingSoon'

export default function UsersPage() {
  return (
    <ComingSoon
      icon={UserCog}
      title="Manage users"
      description="Creating, editing, and managing roles for people in your organization will live here."
      phase="Phase 10"
    />
  )
}
