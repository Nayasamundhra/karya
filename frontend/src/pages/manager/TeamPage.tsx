import { Users } from 'lucide-react'

import { ComingSoon } from '@/components/feedback/ComingSoon'

export default function TeamPage() {
  return (
    <ComingSoon
      icon={Users}
      title="Team attendance"
      description="Today's attendance across your tenant, and per-employee history, will live here."
      phase="Phase 10"
    />
  )
}
