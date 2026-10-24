const FALLBACK = '/campaigns'

// Only same-origin relative paths: blocks "//evil.com", "/\evil.com", absolute URLs and login loops.
export function safeNext(raw: string | null): string {
  if (
    !raw ||
    !raw.startsWith('/') ||
    raw.startsWith('//') ||
    [...raw].some((ch) => ch === '\\' || ch.charCodeAt(0) < 32)
  ) {
    return FALLBACK
  }
  try {
    const url = new URL(raw, window.location.origin)
    if (url.origin !== window.location.origin || url.pathname.startsWith('/login')) return FALLBACK
    return url.pathname + url.search + url.hash
  } catch {
    return FALLBACK
  }
}
