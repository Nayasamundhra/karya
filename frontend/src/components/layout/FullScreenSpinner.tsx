import { Spinner } from '@/components/ui/Spinner'

export function FullScreenSpinner({ label }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <Spinner label={label} className="size-6" />
    </div>
  )
}
