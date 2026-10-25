import { useEffect, useState } from 'react'
import { maskPhone } from '../lib/mask'
import { strings } from '../lib/strings'

const REVEAL_MS = 30_000

// The full number is in the DOM only while revealed. It re-masks after 30 s, when the tab is
// hidden, and on unmount (page change, pagination, sign-out).
export function PhoneCell({ phone }: { phone: string }) {
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    if (!revealed) return
    const hide = () => setRevealed(false)
    const timer = setTimeout(hide, REVEAL_MS)
    const onVisibility = () => document.visibilityState === 'hidden' && hide()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [revealed])

  return (
    <span className="inline-flex items-center gap-2">
      <span className="tabular-nums" data-testid="phone">
        {revealed ? phone : maskPhone(phone)}
      </span>
      <button
        type="button"
        aria-pressed={revealed}
        aria-label={revealed ? strings.phone.hide : strings.phone.reveal}
        title={revealed ? strings.phone.hide : strings.phone.reveal}
        onClick={() => setRevealed((r) => !r)}
        className="relative z-10 rounded p-1 hover:bg-card"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
          <circle cx="12" cy="12" r="3" />
          {revealed && <path d="M3 3l18 18" />}
        </svg>
      </button>
    </span>
  )
}
