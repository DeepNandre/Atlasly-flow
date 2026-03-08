import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ErrorStateProps {
  message?: string
  onRetry?: () => void
}

export function ErrorState({ message = 'Something went wrong', onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div className="rounded-full bg-atlasly-bad/10 p-4">
        <AlertTriangle className="h-8 w-8 text-atlasly-bad" />
      </div>
      <div>
        <p className="font-medium text-atlasly-ink">{message}</p>
        <p className="text-sm text-atlasly-muted mt-1">Check your connection and try again</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
