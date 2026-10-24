import { useCallback, useEffect, useRef, useState } from 'react'

export const WARN_AFTER_MS = 14 * 60_000
export const SIGN_OUT_AFTER_MS = 15 * 60_000
const ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'scroll', 'touchstart'] as const

// Wall-clock based, so a sleeping laptop is signed out as soon as it wakes up.
// Returns the seconds left once the warning is showing, otherwise null.
export function useIdleTimeout(enabled: boolean, onTimeout: () => void) {
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null)
  const lastActivity = useRef(0)
  const warning = useRef(false)
  const timeout = useRef(onTimeout)
  useEffect(() => {
    timeout.current = onTimeout
  })

  const stay = useCallback(() => {
    lastActivity.current = Date.now()
    warning.current = false
    setSecondsLeft(null)
  }, [])

  useEffect(() => {
    if (!enabled) return
    lastActivity.current = Date.now()
    const onActivity = () => {
      if (!warning.current) lastActivity.current = Date.now() // once warned, only the button counts
    }
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }))
    const tick = setInterval(() => {
      const idle = Date.now() - lastActivity.current
      if (idle >= SIGN_OUT_AFTER_MS) {
        clearInterval(tick)
        warning.current = false
        setSecondsLeft(null)
        timeout.current()
      } else if (idle >= WARN_AFTER_MS) {
        warning.current = true
        setSecondsLeft(Math.ceil((SIGN_OUT_AFTER_MS - idle) / 1000))
      }
    }, 1000)
    return () => {
      clearInterval(tick)
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, onActivity))
      warning.current = false
      setSecondsLeft(null) // a sign-out from the warning dialog must not leave it open
    }
  }, [enabled])

  return { secondsLeft, stay }
}
