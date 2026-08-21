import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { ChangePasswordForm } from '@/features/auth/ChangePasswordForm'
import { useOwnProfile } from '@/features/users/useOwnProfile'
import { ProfileForm } from '@/features/users/ProfileForm'
import { TenantSettingsCard } from '@/features/tenant/TenantSettingsCard'
import { useAuth } from '@/features/auth/useAuth'

export default function ProfilePage() {
  const { data: user, isLoading, isError, error, refetch } = useOwnProfile()
  const { hasRole } = useAuth()

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">Profile</h1>

      {isLoading && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-1/3" />
          </CardContent>
        </Card>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {user && (
        <Tabs defaultValue="profile">
          <TabsList>
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="security">Security</TabsTrigger>
            {hasRole('TENANT_ADMIN') && <TabsTrigger value="organization">Organization</TabsTrigger>}
          </TabsList>

          <TabsContent value="profile">
            <Card>
              <CardHeader>
                <CardTitle>Your details</CardTitle>
              </CardHeader>
              <CardContent>
                <ProfileForm user={user} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="security">
            <Card>
              <CardHeader>
                <CardTitle>Change password</CardTitle>
              </CardHeader>
              <CardContent>
                <ChangePasswordForm />
              </CardContent>
            </Card>
          </TabsContent>

          {hasRole('TENANT_ADMIN') && (
            <TabsContent value="organization">
              <TenantSettingsCard />
            </TabsContent>
          )}
        </Tabs>
      )}
    </div>
  )
}
