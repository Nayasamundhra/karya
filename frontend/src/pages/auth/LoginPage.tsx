import { LoginForm } from '@/features/auth/LoginForm'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-sunken p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <span className="flex size-10 items-center justify-center rounded-md bg-accent-600 text-base font-bold text-white">
            K
          </span>
          <h1 className="text-lg font-semibold text-foreground">Sign in to Karya</h1>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Welcome back</CardTitle>
          </CardHeader>
          <CardContent>
            <LoginForm />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
