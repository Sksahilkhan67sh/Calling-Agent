import { screen, within } from '@testing-library/react'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { pollEvery } from '../src/api/queries'
import { setThrottle } from '../src/api/throttle'
import { strings } from '../src/lib/strings'
import { server } from './server'
import { ALL_ROLES, campaign, renderApp } from './utils'

const t = strings.campaigns
const list = (rows: unknown[]) =>
  server.use(http.get('*/v1/campaigns', () => HttpResponse.json(rows)))

const rows = [
  campaign({
    id: 'a1111111-1111-4111-8111-111111111111',
    name: 'Older draft',
    created_at: '2026-10-01T08:00:00Z',
  }),
  campaign({
    id: 'b2222222-2222-4222-8222-222222222222',
    name: 'Newest active',
    status: 'active',
    contact_count: 340,
    created_at: '2026-10-22T08:00:00Z',
  }),
  campaign({
    id: 'c3333333-3333-4333-8333-333333333333',
    name: 'Middle paused',
    status: 'paused',
    created_at: '2026-10-10T08:00:00Z',
  }),
]

test('lists campaigns newest first with status text, counts and a link to each detail page', async () => {
  list(rows)
  const { container } = renderApp('/campaigns')
  const table = await screen.findByRole('table', { name: t.tableLabel })
  const names = within(table)
    .getAllByRole('rowheader')
    .map((c) => c.textContent)
  expect(names).toEqual(['Newest active', 'Middle paused', 'Older draft'])
  const first = within(table).getAllByRole('row')[1]!
  expect(within(first).getByText('Active')).toBeInTheDocument() // text, not only colour
  expect(within(first).getByText('340')).toBeInTheDocument()
  expect(within(first).getByRole('link', { name: 'Newest active' })).toHaveAttribute(
    'href',
    '/campaigns/b2222222-2222-4222-8222-222222222222',
  )
  expect(container.querySelector('time[title="2026-10-22T08:00:00Z"]')).not.toBeNull() // UTC in tooltip
  expect(await axe(container)).toHaveNoViolations()
})

test('the status filter is sent to the server as ?status=', async () => {
  const seen: (string | null)[] = []
  server.use(
    http.get('*/v1/campaigns', ({ request }) => {
      seen.push(new URL(request.url).searchParams.get('status'))
      return HttpResponse.json(rows)
    }),
  )
  const { user } = renderApp('/campaigns')
  await screen.findByRole('table')
  await user.selectOptions(screen.getByLabelText(t.filterStatus), 'active')
  await screen.findByRole('table')
  expect(seen).toEqual([null, 'active'])
})

test('name search filters on the client without another request', async () => {
  let requests = 0
  server.use(
    http.get('*/v1/campaigns', () => {
      requests++
      return HttpResponse.json(rows)
    }),
  )
  const { user } = renderApp('/campaigns')
  await screen.findByRole('table')
  await user.type(screen.getByRole('searchbox', { name: t.search }), 'middle')
  expect(screen.getAllByRole('rowheader')).toHaveLength(1)
  await user.clear(screen.getByRole('searchbox', { name: t.search }))
  await user.type(screen.getByRole('searchbox', { name: t.search }), 'zzz')
  expect(screen.getByText(t.noMatch)).toBeInTheDocument()
  expect(requests).toBe(1)
})

test('Refresh refetches', async () => {
  let requests = 0
  server.use(
    http.get('*/v1/campaigns', () => {
      requests++
      return HttpResponse.json(rows)
    }),
  )
  const { user } = renderApp('/campaigns')
  await screen.findByRole('table')
  await user.click(screen.getByRole('button', { name: t.refresh }))
  await screen.findByRole('button', { name: t.refresh })
  expect(requests).toBe(2)
})

describe('empty state', () => {
  test('staff are offered the next action', async () => {
    list([])
    renderApp('/campaigns', ALL_ROLES.manager)
    expect(await screen.findByText(t.empty)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: t.new })).toHaveLength(2) // header + empty state
  })

  test('Sales see a plain message and no create button', async () => {
    list([])
    renderApp('/campaigns', ALL_ROLES.sales)
    expect(await screen.findByText(t.emptySales)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.new })).not.toBeInTheDocument()
  })
})

test('Sales can read the list but the create button is hidden, not disabled', async () => {
  list(rows)
  renderApp('/campaigns', ALL_ROLES.sales)
  await screen.findByRole('table')
  expect(screen.queryByRole('link', { name: t.new })).not.toBeInTheDocument()
})

test('a failed load shows an error with Retry that recovers', async () => {
  let fail = true
  server.use(
    http.get('*/v1/campaigns', () =>
      fail ? HttpResponse.json({ detail: 'boom' }, { status: 500 }) : HttpResponse.json(rows),
    ),
  )
  const { user } = renderApp('/campaigns')
  expect(await screen.findByRole('alert')).toHaveTextContent(t.loadFailed)
  fail = false
  await user.click(screen.getByRole('button', { name: strings.retry }))
  expect(await screen.findByRole('table')).toBeInTheDocument()
})

test('a 403 from the server is an inline no-access state without a retry button', async () => {
  server.use(
    http.get('*/v1/campaigns', () => HttpResponse.json({ detail: 'nope' }, { status: 403 })),
  )
  renderApp('/campaigns')
  expect(await screen.findByRole('alert')).toHaveTextContent(strings.forbidden.title)
  expect(screen.queryByRole('button', { name: strings.retry })).not.toBeInTheDocument()
})

test('a 429 shows the wait time and pauses polling', async () => {
  server.use(
    http.get('*/v1/campaigns', () =>
      HttpResponse.json({ detail: 'slow' }, { status: 429, headers: { 'Retry-After': '12' } }),
    ),
  )
  renderApp('/campaigns')
  expect(await screen.findByText(/Automatic refreshing is paused for 1\d s/)).toBeInTheDocument()
  expect(pollEvery(30_000)()).toBe(false)
})

describe('pollEvery', () => {
  const visibility = (v: DocumentVisibilityState) =>
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => v })
  afterEach(() => visibility('visible'))

  test('polls while visible', () => expect(pollEvery(30_000)()).toBe(30_000))

  test('stops while the tab is hidden', () => {
    visibility('hidden')
    expect(pollEvery(30_000)()).toBe(false)
  })

  test('stops while throttled', () => {
    setThrottle(5)
    expect(pollEvery(30_000)()).toBe(false)
  })
})
