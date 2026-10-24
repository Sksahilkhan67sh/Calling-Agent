import { useSyncExternalStore } from 'react'
import { strings } from '../lib/strings'

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

export function OfflineBanner() {
  const online = useSyncExternalStore(subscribe, () => navigator.onLine)
  if (online) return null
  return (
    <div role="status" className="bg-danger px-4 py-2 text-center text-sm text-bg">
      {strings.offline}
    </div>
  )
}
