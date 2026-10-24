import { ApiError } from '../api/api'
import { strings } from '../lib/strings'
import { Button } from './Button'

// 403 is "logged in but not allowed" and is never offered a retry; everything else can be retried.
export function ErrorState({
  error,
  message,
  onRetry,
}: {
  error: unknown
  message: string
  onRetry: () => void
}) {
  const forbidden = error instanceof ApiError && error.status === 403
  return (
    <div role="alert" className="rounded-md border border-danger p-4">
      <p className="font-medium">{forbidden ? strings.forbidden.title : message}</p>
      <p className="mt-1 text-sm text-muted">
        {forbidden
          ? strings.forbidden.body
          : error instanceof ApiError
            ? error.message
            : strings.api.generic}
      </p>
      {!forbidden && (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          {strings.retry}
        </Button>
      )}
    </div>
  )
}
