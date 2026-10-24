import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { strings } from '../src/lib/strings'
import type { QueryClient } from '@tanstack/react-query'
import { server, unauthorized } from './server'
import { ALL_ROLES, campaign, renderApp, renderRaw } from './utils'

const t = strings.login
// A disabled, empty placeholder for the current user may exist; no fetched data may survive.
const cacheHoldsNoData = (qc: QueryClient) =>
  qc
    .getQueryCache()
    .getAll()
    .every((q) => q.state.data === undefined)
const listOk = () => server.use(http.get('*/v1/campaigns', () => HttpResponse.json([campaign()])))

// Server whose /me answers 401 until a login has happened, like the real backend.
function loginServer(roles = ALL_ROLES.admin) {
  const state = { signedIn: false, body: undefined as unknown, loginStatus: 200 }
  server.use(
    http.get('*/v1/auth/me', () =>
      state.signedIn ? HttpResponse.json({ id: 1, username: 'sahil', roles }) : unauthorized(),
    ),
    http.post('*/v1/auth/token', async ({ request }) => {
      state.body = await request.json()
      if (state.loginStatus !== 200) {
        return state.loginStatus === 429
          ? HttpResponse.json({ detail: 'locked' }, { status: 429 })
          : HttpResponse.json({ detail: 'Authentication failed.' }, { status: 401 })
      }
      state.signedIn = true
      return HttpResponse.json({ detail: 'ok' })
    }),
  )
  server.use(http.post('*/v1/auth/token/refresh', unauthorized))
  listOk()
  return state
}

async function fillLogin(user: ReturnType<typeof renderApp>['user'], mfa = '') {
  await user.type(await screen.findByLabelText(t.username), 'sahil')
  await user.type(screen.getByLabelText(t.password), 'hunter2')
  if (mfa) await user.type(screen.getByLabelText(t.mfa), mfa)
  await user.click(screen.getByRole('button', { name: t.submit }))
}

describe('login', () => {
  test('shows the three fields with MFA helper text and one-time-code semantics', async () => {
    const { container } = renderApp('/login', null)
    const mfa = await screen.findByLabelText(t.mfa)
    expect(mfa).toHaveAttribute('autocomplete', 'one-time-code')
    expect(mfa).toHaveAttribute('inputmode', 'numeric')
    expect(screen.getByText(t.mfaHelp)).toBeInTheDocument()
    expect(screen.getByLabelText(t.password)).toHaveAttribute('type', 'password')
    expect(await axe(container)).toHaveNoViolations()
  })

  test('toggles password visibility and warns about Caps Lock', async () => {
    const { user } = renderApp('/login', null)
    const password = await screen.findByLabelText(t.password)
    await user.click(screen.getByRole('button', { name: t.show }))
    expect(password).toHaveAttribute('type', 'text')
    fireEvent.keyDown(password, { key: 'A', modifierCapsLock: true })
    expect(screen.getByText(t.capsLock)).toBeInTheDocument()
  })

  test('signs in, sends the MFA code only when given, and lands on campaigns', async () => {
    const state = loginServer()
    const { user, router } = renderRaw('/login')
    await fillLogin(user, '123456')
    expect(
      await screen.findByRole('heading', { name: strings.campaigns.title }),
    ).toBeInTheDocument()
    expect(state.body).toEqual({ username: 'sahil', password: 'hunter2', mfa_code: '123456' })
    expect(router.state.location.pathname).toBe('/campaigns')
  })

  test('omits an empty MFA code (Sales users)', async () => {
    const state = loginServer(ALL_ROLES.sales)
    const { user } = renderRaw('/login')
    await fillLogin(user)
    await screen.findByRole('heading', { name: strings.campaigns.title })
    expect(state.body).toEqual({ username: 'sahil', password: 'hunter2' })
  })

  test('401 shows one generic message and clears the secrets', async () => {
    const state = loginServer()
    state.loginStatus = 401
    const { user } = renderRaw('/login')
    await fillLogin(user, '123456')
    expect(await screen.findByRole('alert')).toHaveTextContent(t.invalid)
    expect(screen.getByLabelText(t.password)).toHaveValue('')
    expect(screen.getByLabelText(t.mfa)).toHaveValue('')
  })

  test('429 (throttled or locked out) shows the try-later message', async () => {
    loginServer().loginStatus = 429
    const { user } = renderRaw('/login')
    await fillLogin(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(t.tooMany)
  })

  test('a malformed MFA code is rejected before any request', async () => {
    const state = loginServer()
    const { user } = renderRaw('/login')
    await fillLogin(user, '12ab')
    expect(await screen.findByText(t.mfaInvalid)).toBeInTheDocument()
    expect(state.body).toBeUndefined()
  })

  test('submit is disabled while the request is in flight', async () => {
    let calls = 0
    loginServer()
    server.use(
      http.post('*/v1/auth/token', async () => {
        calls++
        await new Promise((r) => setTimeout(r, 100))
        return HttpResponse.json({ detail: 'ok' }, { status: 401 })
      }),
    )
    const { user } = renderRaw('/login')
    await user.type(await screen.findByLabelText(t.username), 'sahil')
    await user.type(screen.getByLabelText(t.password), 'x')
    await user.click(screen.getByRole('button', { name: t.submit }))
    expect(screen.getByRole('button', { name: t.submitting })).toBeDisabled()
    await screen.findByRole('alert')
    expect(calls).toBe(1)
  })

  test('follows a safe next= and ignores an open-redirect next=', async () => {
    loginServer()
    const first = renderRaw('/login?next=%2Fcampaigns%2Fnew')
    await fillLogin(first.user)
    await screen.findByRole('heading', { name: strings.createCampaign.title })
    expect(first.router.state.location.pathname).toBe('/campaigns/new')
    first.unmount()

    loginServer()
    const second = renderRaw('/login?next=%2F%2Fevil.com')
    await fillLogin(second.user)
    await screen.findByRole('heading', { name: strings.campaigns.title })
    expect(second.router.state.location.pathname).toBe('/campaigns')
  })

  test('a signed-in visitor is redirected away from /login', async () => {
    listOk()
    const { router } = renderApp('/login')
    await screen.findByRole('heading', { name: strings.campaigns.title })
    expect(router.state.location.pathname).toBe('/campaigns')
  })
})

test('an anonymous visitor is sent to login with the page they wanted', async () => {
  const { router } = renderApp('/campaigns/new', null)
  expect(await screen.findByLabelText(t.username)).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/login')
  expect(router.state.location.search).toBe('?next=%2Fcampaigns%2Fnew')
})

describe('role gating', () => {
  test.each([
    ['Sales', ALL_ROLES.sales],
    ['a user with no role', []],
  ])('%s cannot open the create page', async (_name, roles) => {
    const { router } = renderApp('/campaigns/new', roles)
    expect(
      await screen.findByRole('heading', { name: strings.forbidden.title }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/campaigns/new') // inline 403, not a redirect
  })

  test('Campaign Managers can open the create page', async () => {
    renderApp('/campaigns/new', ALL_ROLES.manager)
    expect(
      await screen.findByRole('heading', { name: strings.createCampaign.title }),
    ).toBeInTheDocument()
  })

  test('a user with no role cannot open the campaign list', async () => {
    renderApp('/campaigns', [])
    expect(
      await screen.findByRole('heading', { name: strings.forbidden.title }),
    ).toBeInTheDocument()
  })
})

describe('sign out', () => {
  test('calls the server with CSRF, clears the cache, signals other tabs and goes to login', async () => {
    document.cookie = 'csrftoken=tok; path=/'
    listOk()
    let csrf: string | null = null
    server.use(
      http.post('*/v1/auth/logout', ({ request }) => {
        csrf = request.headers.get('x-csrftoken')
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const other = new BroadcastChannel('calling-agent-auth')
    const received: unknown[] = []
    other.onmessage = (e) => received.push(e.data)

    const { user, queryClient, router } = renderApp('/campaigns')
    await screen.findByText(campaign().name)
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: 'sahil' }))
    await user.click(await screen.findByRole('menuitem', { name: strings.userMenu.signOut }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(cacheHoldsNoData(queryClient)).toBe(true)
    await waitFor(() => expect(csrf).toBe('tok'))
    await waitFor(() => expect(received).toEqual(['logged-out'])) // a signal only, no data
    other.close()
  })

  test('another tab signing out signs this one out without calling the server', async () => {
    listOk()
    let logoutCalls = 0
    server.use(
      http.post('*/v1/auth/logout', () => {
        logoutCalls++
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { queryClient, router } = renderApp('/campaigns')
    await screen.findByText(campaign().name)

    const other = new BroadcastChannel('calling-agent-auth')
    other.postMessage('logged-out')
    other.close()

    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(cacheHoldsNoData(queryClient)).toBe(true)
    expect(logoutCalls).toBe(0)
  })

  test('a failed refresh mid-session shows the expired dialog, then clears everything', async () => {
    let signedIn = true
    server.use(
      http.get('*/v1/auth/me', () =>
        signedIn
          ? HttpResponse.json({ id: 1, username: 'sahil', roles: ['Admin'] })
          : unauthorized(),
      ),
      http.get('*/v1/campaigns', () => unauthorized()),
      http.post('*/v1/auth/token/refresh', unauthorized),
    )
    const { user, queryClient, router } = renderRaw('/campaigns')
    expect(await screen.findByRole('alertdialog')).toHaveTextContent(strings.expired.title)
    signedIn = false
    await user.click(screen.getByRole('button', { name: strings.expired.action }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe('?next=%2Fcampaigns')
    expect(cacheHoldsNoData(queryClient)).toBe(true)
  })
})

describe('idle timeout', () => {
  beforeEach(() => {
    // Only the interval and the clock are faked so network mocks and Testing Library keep working.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  })
  afterEach(() => vi.useRealTimers())

  const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms))

  test('warns at 14 minutes, lets the user stay, then signs out at 15 minutes of silence', async () => {
    listOk()
    let logoutCalls = 0
    server.use(
      http.post('*/v1/auth/logout', () => {
        logoutCalls++
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { router } = renderApp('/campaigns')
    await screen.findByText(campaign().name)

    await advance(13 * 60_000)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()

    await advance(61_000)
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent(/signed out in \d+ seconds/)

    fireEvent.click(screen.getByRole('button', { name: strings.idle.stay }))
    await advance(1000)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()

    await advance(14 * 60_000 + 1000)
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    await advance(60_000)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(logoutCalls).toBe(1)
  })

  test('activity before the warning resets the clock', async () => {
    listOk()
    renderApp('/campaigns')
    await screen.findByText(campaign().name)
    await advance(13 * 60_000)
    fireEvent.pointerDown(window)
    await advance(13 * 60_000)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })
})
