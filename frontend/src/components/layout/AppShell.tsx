import { Outlet } from 'react-router-dom'

import { BottomNav } from '@/components/layout/BottomNav'
import { Header } from '@/components/layout/Header'
import { OfflineBanner } from '@/components/layout/OfflineBanner'
import { Sidebar } from '@/components/layout/Sidebar'

/**
 * The role-aware shell every authenticated route renders inside (mounted by
 * the `/` route in `router.tsx`, wrapping `RequireAuth`'s `<Outlet/>`).
 * Desktop: persistent sidebar + header. Mobile: header + fixed bottom nav,
 * with the content area padded to clear the bottom nav's height so nothing
 * sits behind it — this is the "design mobile intentionally" requirement
 * from §8, not a shrunk desktop layout.
 */
export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <OfflineBanner />
      <div className="flex flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main id="main-content" className="flex-1 overflow-x-hidden p-4 pb-20 sm:p-6 lg:pb-6">
            <Outlet />
          </main>
        </div>
      </div>
      <BottomNav />
    </div>
  )
}
