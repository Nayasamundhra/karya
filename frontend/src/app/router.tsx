import { lazy, Suspense, type ComponentType } from 'react'
import type { RouteObject } from 'react-router-dom'
import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { FullScreenSpinner } from '@/components/layout/FullScreenSpinner'
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
 * What a signed-out visitor sees at `/` (see `RequireAuth`'s `anonymousRoot`).
 * `React.lazy` + `Suspense` here because this sits outside the data router's
 * own `lazy()` route field — a signed-in user's bundle never loads it.
 */
const LandingPage = lazy(() => import('@/pages/LandingPage'))
const landingRoot = (
  <Suspense fallback={<FullScreenSpinner label="Loading…" />}>
    <LandingPage />
  </Suspense>
)

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
    element: <RequireAuth anonymousRoot={landingRoot} />,
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
              { path: 'team/hours', lazy: lazyRoute(() => import('@/pages/manager/TeamHoursPage')) },
              { path: 'team/:userId', lazy: lazyRoute(() => import('@/pages/manager/EmployeeDetailPage')) },
            ],
          },
          {
            // Organization settings and the attendance location (renaming
            // the tenant, moving the geofence, regenerating the QR) are all
            // admin-level decisions — MANAGER has no route here at all.
            element: <RequireRole roles={['TENANT_ADMIN']} />,
            children: [
              { path: 'admin/organization', lazy: lazyRoute(() => import('@/pages/admin/OrganizationPage')) },
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
