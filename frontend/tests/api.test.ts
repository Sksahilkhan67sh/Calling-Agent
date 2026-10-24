import { http, HttpResponse } from 'msw'
import { ApiError, api, setAuthLostHandler } from '../src/api/api'
import { throttleSecondsLeft } from '../src/api/throttle'
import { server } from './server'

const expired = () => HttpResponse.json({ detail: 'expired' }, { status: 401 })

afterEach(() => setAuthLostHandler(undefined))

test('sends the CSRF header from the cookie on writes only', async () => {
  document.cookie = 'csrftoken=abc123; path=/'
  const seen: Record<string, string | null> = {}
  server.use(
    http.get('*/v1/x', ({ request }) => {
      seen.get = request.headers.get('x-csrftoken')
      return HttpResponse.json({})
    }),
    http.post('*/v1/x', ({ request }) => {
      seen.post = request.headers.get('x-csrftoken')
      return HttpResponse.json({})
    }),
  )
  await api('/v1/x')
  await api('/v1/x', { method: 'POST', json: {} })
  expect(seen).toEqual({ get: null, post: 'abc123' })
})

test('concurrent 401s trigger exactly one refresh and each request replays once', async () => {
  let refreshed = false
  const hits = { refresh: 0, a: 0, b: 0, c: 0 }
  const guarded = (key: 'a' | 'b' | 'c') =>
    http.get(`*/v1/${key}`, () => {
      hits[key]++
      return refreshed ? HttpResponse.json({ ok: key }) : expired()
    })
  server.use(
    guarded('a'),
    guarded('b'),
    guarded('c'),
    http.post('*/v1/auth/token/refresh', async () => {
      hits.refresh++
      await new Promise((r) => setTimeout(r, 20))
      refreshed = true
      return HttpResponse.json({ detail: 'ok' })
    }),
  )
  const results = await Promise.all([api('/v1/a'), api('/v1/b'), api('/v1/c')])
  expect(results).toEqual([{ ok: 'a' }, { ok: 'b' }, { ok: 'c' }])
  expect(hits).toEqual({ refresh: 1, a: 2, b: 2, c: 2 })
})

test('a failed refresh signals auth loss, never loops, and surfaces the 401', async () => {
  const lost = vi.fn()
  setAuthLostHandler(lost)
  let calls = 0
  let refreshes = 0
  server.use(
    http.get('*/v1/x', () => {
      calls++
      return expired()
    }),
    http.post('*/v1/auth/token/refresh', () => {
      refreshes++
      return expired()
    }),
  )
  await expect(api('/v1/x')).rejects.toMatchObject({ status: 401 })
  expect({ calls, refreshes }).toEqual({ calls: 1, refreshes: 1 })
  expect(lost).toHaveBeenCalledTimes(1)
})

test('a replay that is still 401 does not start another refresh', async () => {
  let calls = 0
  let refreshes = 0
  server.use(
    http.get('*/v1/x', () => {
      calls++
      return expired()
    }),
    http.post('*/v1/auth/token/refresh', () => {
      refreshes++
      return HttpResponse.json({ detail: 'ok' })
    }),
  )
  await expect(api('/v1/x')).rejects.toMatchObject({ status: 401 })
  expect({ calls, refreshes }).toEqual({ calls: 2, refreshes: 1 })
})

test('skipRefresh requests (login) never refresh', async () => {
  let refreshes = 0
  server.use(
    http.post('*/v1/auth/token', expired),
    http.post('*/v1/auth/token/refresh', () => {
      refreshes++
      return HttpResponse.json({})
    }),
  )
  await expect(
    api('/v1/auth/token', { method: 'POST', json: {}, skipRefresh: true }),
  ).rejects.toMatchObject({
    status: 401,
  })
  expect(refreshes).toBe(0)
})

test('429 reads Retry-After, pauses polling state and is reported as an ApiError', async () => {
  server.use(
    http.get('*/v1/x', () =>
      HttpResponse.json({ detail: 'slow down' }, { status: 429, headers: { 'Retry-After': '42' } }),
    ),
  )
  await expect(api('/v1/x')).rejects.toMatchObject({ status: 429, retryAfter: 42 })
  expect(throttleSecondsLeft()).toBeGreaterThan(40)
})

test('a GET is retried once on a network error, a POST never', async () => {
  const counts = { get: 0, post: 0 }
  server.use(
    http.get('*/v1/x', () => {
      counts.get++
      return HttpResponse.error()
    }),
    http.post('*/v1/x', () => {
      counts.post++
      return HttpResponse.error()
    }),
  )
  await expect(api('/v1/x')).rejects.toMatchObject({ status: 0, code: 'network' })
  await expect(api('/v1/x', { method: 'POST', json: {} })).rejects.toMatchObject({
    code: 'network',
  })
  expect(counts).toEqual({ get: 2, post: 1 })
})

test('errors are normalised: code, message and field errors', async () => {
  server.use(
    http.post('*/v1/x', () =>
      HttpResponse.json(
        {
          code: 'no_valid_contacts',
          message: 'No valid contacts found in the file.',
          name: ['Too long.'],
          contact_file: 'Bad file.',
        },
        { status: 400 },
      ),
    ),
  )
  const error = await api('/v1/x', { method: 'POST', json: {} }).catch((e: unknown) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error).toMatchObject({
    status: 400,
    code: 'no_valid_contacts',
    message: 'No valid contacts found in the file.',
    fieldErrors: { name: ['Too long.'], contact_file: ['Bad file.'] },
  })
})

test('204 resolves to undefined and non-JSON error bodies get a generic message', async () => {
  server.use(
    http.post('*/v1/ok', () => new HttpResponse(null, { status: 204 })),
    http.get('*/v1/boom', () => new HttpResponse('<html>oops</html>', { status: 500 })),
  )
  await expect(api('/v1/ok', { method: 'POST' })).resolves.toBeUndefined()
  await expect(api('/v1/boom')).rejects.toMatchObject({
    status: 500,
    message: 'Something went wrong. Try again.',
  })
})

test('nested serializer errors are flattened to dotted field names', async () => {
  server.use(
    http.post('*/v1/x', () =>
      HttpResponse.json(
        { retry_policy: { max_retries: ['Too big.'], non_field_errors: ['Bad.'] }, name: ['Req.'] },
        { status: 400 },
      ),
    ),
  )
  const error = await api('/v1/x', { method: 'POST', json: {} }).catch((e: unknown) => e)
  expect(error).toMatchObject({
    fieldErrors: {
      'retry_policy.max_retries': ['Too big.'],
      'retry_policy.non_field_errors': ['Bad.'],
      name: ['Req.'],
    },
  })
})
