import type { ComponentType } from 'react'
import type { RouteObject } from 'react-router-dom'
import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from '@/routes/guards'

/**
 * Route-level code splitting (§21): every page is a separate chunk, loaded
 * only when its route is actually visited. A STAFF user's bundle never
 * pulls in `pages/admin/*` — there is no `import` anywhere in their render
 * path that reaches it. `lazy()` here is React Router's own data-router
 * field (not `React.lazy`) — it wants a module exporting `Component`, so
 * this adapts our pages' plain `export default` to that shape in one place.
 */
function lazyRoute(importer: () => Promise<{ default: ComponentType }>) {
  return async () => {
    const { default: Component } = await importer()
    return { Component }
  }
}

/**
 * The route tree, exported separately from the browser router instance
 * below so tests can feed it to `createMemoryRouter` with an arbitrary
 * starting path instead of fighting `window.history` — see
 * `tests/unit/routing.test.tsx`.
 */
export const routes: RouteObject[] = [
  {
    path: '/login',
    lazy: async () => {
      const { default: LoginPage } = await import('@/pages/auth/LoginPage')
      return {
        Component: () => (
          <RedirectIfAuthenticated>
            <LoginPage />
          </RedirectIfAuthenticated>
        ),
      }
    },
  },
  {
    path: '/onboarding',
    lazy: async () => {
      const { default: CreateOrganizationPage } = await import(
        '@/pages/onboarding/CreateOrganizationPage'
      )
      return {
        Component: () => (
          <RedirectIfAuthenticated>
            <CreateOrganizationPage />
          </RedirectIfAuthenticated>
        ),
      }
    },
  },
  {
    // No RedirectIfAuthenticated here on purpose: verification must resolve
    // to a fresh session regardless of whatever session (if any) happened
    // to already exist in this browser, since the token in the URL is what
    // actually decides who this becomes.
    path: '/onboarding/verify',
    lazy: async () => {
      const { default: VerifyEmailPage } = await import('@/pages/onboarding/VerifyEmailPage')
      return { Component: VerifyEmailPage }
    },
  },
  {
    // The office-display kiosk is a public, standalone screen — no login,
    // no app shell, no nav. It authenticates itself with its own display
    // token (see `src/features/display/`), never a user session.
    path: '/display',
    lazy: async () => {
      const { default: KioskPage } = await import('@/pages/display/KioskPage')
      return { Component: KioskPage }
    },
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, lazy: lazyRoute(() => import('@/pages/HomePage')) },
          {
            element: <RequireRole roles={['TENANT_ADMIN']} />,
            children: [
              { path: 'setup', lazy: lazyRoute(() => import('@/pages/onboarding/SetupChecklistPage')) },
            ],
          },
          { path: 'attendance', lazy: lazyRoute(() => import('@/pages/staff/AttendancePage')) },
          { path: 'attendance/check-in', lazy: lazyRoute(() => import('@/pages/staff/CheckInPage')) },
          { path: 'attendance/check-out', lazy: lazyRoute(() => import('@/pages/staff/CheckOutPage')) },
          { path: 'profile', lazy: lazyRoute(() => import('@/pages/ProfilePage')) },
          {
            element: <RequireRole roles={['MANAGER', 'TENANT_ADMIN']} />,
            children: [
              { path: 'team', lazy: lazyRoute(() => import('@/pages/manager/TeamPage')) },
              { path: 'team/:userId', lazy: lazyRoute(() => import('@/pages/manager/EmployeeDetailPage')) },
              // MANAGER is one of `QR_ISSUER_ROLES` on the backend — it may
              // create/list/revoke display tokens exactly like TENANT_ADMIN.
              // `OrganizationPage` itself narrows what a MANAGER actually
              // sees to just the Displays tab; the Details/Location tabs
              // (renaming the tenant, moving the geofence) stay admin-only.
              { path: 'admin/organization', lazy: lazyRoute(() => import('@/pages/admin/OrganizationPage')) },
            ],
          },
          {
            element: <RequireRole roles={['TENANT_ADMIN']} />,
            children: [
              { path: 'admin/users', lazy: lazyRoute(() => import('@/pages/admin/UsersPage')) },
            ],
          },
          { path: 'forbidden', lazy: lazyRoute(() => import('@/pages/ForbiddenPage')) },
        ],
      },
    ],
  },
  { path: '*', lazy: lazyRoute(() => import('@/pages/NotFoundPage')) },
]

export const router = createBrowserRouter(routes)
