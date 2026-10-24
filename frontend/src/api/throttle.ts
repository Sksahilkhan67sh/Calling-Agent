// Shared "server said slow down" state: polling pauses and the UI shows the wait time.
let until = 0
let ticker: ReturnType<typeof setInterval> | undefined
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

export const DEFAULT_THROTTLE_SECONDS = 30

function stopTicker() {
  clearInterval(ticker)
  ticker = undefined
}

export function setThrottle(seconds: number | undefined) {
  until = Date.now() + (seconds ?? DEFAULT_THROTTLE_SECONDS) * 1000
  // Tick once a second so the countdown re-renders, and stop when it reaches zero.
  ticker ??= setInterval(() => {
    if (!isThrottled()) stopTicker()
    emit()
  }, 1000)
  emit()
}

export function resetThrottle() {
  until = 0
  stopTicker()
  emit()
}

export const isThrottled = () => Date.now() < until
export const throttleSecondsLeft = () => Math.max(0, Math.ceil((until - Date.now()) / 1000))

export function subscribeThrottle(l: () => void) {
  listeners.add(l)
  return () => listeners.delete(l)
}
