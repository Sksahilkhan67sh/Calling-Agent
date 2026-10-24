import { strings } from '../lib/strings'
import { setThrottle } from './throttle'

const TIMEOUT_MS = 30_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string | undefined
  readonly fieldErrors: Record<string, string[]>
  readonly retryAfter: number | undefined

  constructor(
    status: number,
    message: string,
    code?: string,
    fieldErrors: Record<string, string[]> = {},
    retryAfter?: number,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
    this.retryAfter = retryAfter
  }
}

interface Options {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  json?: unknown
  form?: FormData
  signal?: AbortSignal | undefined
  // Login, refresh and logout must never trigger a refresh themselves.
  skipRefresh?: boolean
}

let onAuthLost: (() => void) | undefined
export const setAuthLostHandler = (fn: (() => void) | undefined) => {
  onAuthLost = fn
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match?.[1] ? decodeURIComponent(match[1]) : ''
}

function toTransportError(e: unknown): unknown {
  if (e instanceof DOMException && e.name === 'TimeoutError') {
    return new ApiError(0, strings.api.timeout, 'timeout')
  }
  if (e instanceof TypeError) return new ApiError(0, strings.api.network, 'network')
  return e // caller-initiated abort: let it propagate untouched
}

async function send(path: string, o: Options): Promise<Response> {
  const method = o.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (method !== 'GET') headers['X-CSRFToken'] = csrfToken()
  let body: BodyInit | undefined
  if (o.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(o.json)
  } else if (o.form) {
    body = o.form
  }
  const signals = [AbortSignal.timeout(TIMEOUT_MS), ...(o.signal ? [o.signal] : [])]
  const attempt = () =>
    fetch(new URL(path, window.location.origin), {
      method,
      headers,
      ...(body !== undefined && { body }),
      credentials: 'include',
      signal: AbortSignal.any(signals),
    })
  try {
    return await attempt()
  } catch (e) {
    // One retry for reads on a dropped connection. Writes are never retried automatically.
    if (method === 'GET' && e instanceof TypeError) {
      try {
        return await attempt()
      } catch (e2) {
        throw toTransportError(e2)
      }
    }
    throw toTransportError(e)
  }
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined
  const seconds = Number(value)
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds)
  const date = Date.parse(value)
  return Number.isNaN(date) ? undefined : Math.max(0, Math.ceil((date - Date.now()) / 1000))
}

async function toApiError(res: Response): Promise<ApiError> {
  let parsed: unknown = null
  try {
    parsed = await res.json()
  } catch {
    // Non-JSON error body: fall back to the generic message.
  }
  const body: Record<string, unknown> =
    parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {}
  const code = typeof body.code === 'string' ? body.code : undefined
  const message =
    typeof body.message === 'string'
      ? body.message
      : typeof body.detail === 'string'
        ? body.detail
        : strings.api.generic
  const fieldErrors: Record<string, string[]> = {}
  if (res.status === 400) {
    // Nested serializer errors ({retry_policy: {max_retries: [...]}}) are flattened to "retry_policy.max_retries"
    const collect = (prefix: string, value: unknown) => {
      if (value && typeof value === 'object' && !Array.isArray(value))
        return Object.entries(value).forEach(([k, v]) => collect(prefix ? `${prefix}.${k}` : k, v))
      const messages = (Array.isArray(value) ? value : [value]).filter(
        (v): v is string => typeof v === 'string',
      )
      if (messages.length) fieldErrors[prefix] = messages
    }
    for (const [key, value] of Object.entries(body)) {
      if (key !== 'code' && key !== 'message' && key !== 'detail') collect(key, value)
    }
  }
  return new ApiError(
    res.status,
    message,
    code,
    fieldErrors,
    parseRetryAfter(res.headers.get('Retry-After')),
  )
}

// Single-flight refresh: concurrent 401s share one refresh call. The counter lets a request that
// was already in flight when a refresh finished replay without starting a second refresh.
let refreshing: Promise<boolean> | null = null
let refreshCount = 0

function refreshOnce(): Promise<boolean> {
  refreshing ??= send('/v1/auth/token/refresh', { method: 'POST' })
    .then((r) => {
      if (r.ok) refreshCount++
      return r.ok
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

export async function api<T>(path: string, o: Options = {}): Promise<T> {
  const epoch = refreshCount
  let res = await send(path, o)
  if (res.status === 401 && !o.skipRefresh) {
    if (refreshCount !== epoch || (await refreshOnce())) res = await send(path, o) // replay exactly once
    if (res.status === 401) onAuthLost?.()
  }
  if (!res.ok) {
    const error = await toApiError(res)
    if (res.status === 429) setThrottle(error.retryAfter)
    throw error
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}
