import { useSyncExternalStore } from 'react'
import { subscribeThrottle, throttleSecondsLeft } from '../api/throttle'
import { strings } from '../lib/strings'

export function ThrottleBanner() {
  const seconds = useSyncExternalStore(subscribeThrottle, throttleSecondsLeft)
  if (seconds <= 0) return null
  return (
    <div role="status" className="border-b border-border bg-card px-4 py-2 text-center text-sm">
      {strings.throttled(seconds)}
    </div>
  )
}
