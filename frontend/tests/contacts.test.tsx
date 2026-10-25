import { screen, waitFor, within } from '@testing-library/react'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { CONTACT_STATUSES } from '../src/api/types'
import { strings } from '../src/lib/strings'
import { server } from './server'
import { ALL_ROLES, campaign, renderApp } from './utils'

const t = strings.contacts
const CID = '6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d'
const path = `/campaigns/${CID}`

const contact = (n: number, over: Record<string, unknown> = {}) => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  campaign_id: CID,
  phone_number: `+9198765${String(40000 + n)}`,
  status: 'Pending',
  attempt_count: 0,
  created_at: '2026-10-20T08:30:00Z',
  ...over,
})

function mockContacts(
  handler: (q: URLSearchParams) => { total: number; page: number; items: unknown[] } | Response,
) {
  const seen: URLSearchParams[] = []
  server.use(
    http.get(`*/v1/campaigns/${CID}`, () => HttpResponse.json(campaign({ id: CID }))),
    http.get(`*/v1/campaigns/${CID}/contacts`, ({ request }) => {
      const q = new URL(request.url).searchParams
      seen.push(q)
      const out = handler(q)
      return out instanceof Response ? out : HttpResponse.json(out)
    }),
  )
  return seen
}
const pageOf = (total: number) => (q: URLSearchParams) => {
  const page = Number(q.get('page') ?? 1)
  const size = Number(q.get('page_size') ?? 50)
  const n = Math.max(0, Math.min(size, total - (page - 1) * size))
  return { total, page, items: Array.from({ length: n }, (_, i) => contact((page - 1) * size + i)) }
}

test('lists contacts with masked phones, status, attempts and a link to each contact', async () => {
  mockContacts(() => ({
    total: 2,
    page: 1,
    items: [
      contact(1, { status: 'Completed', attempt_count: 3 }),
      contact(2, { status: 'InConversation' }),
    ],
  }))
  const { container } = renderApp(path)
  const table = await screen.findByRole('table', { name: t.tableLabel })
  expect(within(table).getAllByTestId('phone')[0]).toHaveTextContent('+91•••••')
  expect(within(table).getByText('Completed')).toBeInTheDocument()
  expect(within(table).getByText('In conversation')).toBeInTheDocument()
  expect(within(table).getByText('3')).toBeInTheDocument()
  const links = within(table).getAllByRole('link', { name: t.view })
  expect(links[0]).toHaveAttribute('href', `/contacts/${contact(1).id}`)
  // Full numbers are in the API response but never in the page
  expect(container.innerHTML).not.toContain('9876540001')
  expect(await axe(container)).toHaveNoViolations()
})

test('revealing one row shows only that number', async () => {
  mockContacts(() => ({ total: 2, page: 1, items: [contact(1), contact(2)] }))
  const { user } = renderApp(path)
  await screen.findByRole('table')
  await user.click(screen.getAllByRole('button', { name: strings.phone.reveal })[0]!)
  const phones = screen.getAllByTestId('phone').map((p) => p.textContent)
  expect(phones[0]).toBe(contact(1).phone_number)
  expect(phones[1]).toContain('•••••')
})

test('the status filter offers all nine statuses and is sent as ?status=', async () => {
  const seen = mockContacts(() => ({ total: 0, page: 1, items: [] }))
  const { user } = renderApp(path)
  const select = await screen.findByLabelText(t.status)
  expect(within(select).getAllByRole('option')).toHaveLength(CONTACT_STATUSES.length + 1)
  await user.selectOptions(select, 'RetryScheduled')
  await waitFor(() => expect(seen.at(-1)?.get('status')).toBe('RetryScheduled'))
  expect(await screen.findByText(t.noMatch)).toBeInTheDocument()
})

test('page size is sent as page_size and returns to page 1', async () => {
  const seen = mockContacts(pageOf(300))
  const { user } = renderApp(`${path}?tab=contacts&page=2`)
  await screen.findByRole('table')
  expect(seen.at(-1)?.get('page')).toBe('2')
  await user.selectOptions(screen.getByLabelText(t.pageSize), '100')
  await waitFor(() => expect(seen.at(-1)?.get('page_size')).toBe('100'))
  expect(seen.at(-1)?.get('page')).toBe('1')
})

test('pagination: x–y of total, first/prev/next/last and disabled edges', async () => {
  mockContacts(pageOf(120))
  const { user } = renderApp(path)
  expect(await screen.findByText(t.range(1, 50, 120))).toBeInTheDocument()
  expect(screen.getByRole('button', { name: t.firstPage })).toBeDisabled()
  expect(screen.getByRole('button', { name: t.prevPage })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: t.nextPage }))
  expect(await screen.findByText(t.range(51, 100, 120))).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: t.lastPage }))
  expect(await screen.findByText(t.range(101, 120, 120))).toBeInTheDocument()
  expect(screen.getByRole('button', { name: t.nextPage })).toBeDisabled()
  expect(screen.getByRole('button', { name: t.lastPage })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: t.firstPage }))
  expect(await screen.findByText(t.range(1, 50, 120))).toBeInTheDocument()
})

test('deep links carry status and page; junk values fall back to the defaults', async () => {
  const seen = mockContacts(pageOf(500))
  renderApp(`${path}?tab=contacts&status=Completed&page=3&size=25`)
  await screen.findByRole('table')
  expect(Object.fromEntries(seen.at(-1)!)).toEqual({
    status: 'Completed',
    page: '3',
    page_size: '25',
  })
})

test('junk query values are ignored', async () => {
  const seen = mockContacts(pageOf(10))
  renderApp(`${path}?tab=contacts&status=<script>&size=7&page=-3`)
  await screen.findByRole('table')
  expect(Object.fromEntries(seen.at(-1)!)).toEqual({ page: '1', page_size: '50' })
})

test('an empty campaign shows the empty state', async () => {
  mockContacts(() => ({ total: 0, page: 1, items: [] }))
  renderApp(path)
  expect(await screen.findByText(t.empty)).toBeInTheDocument()
})

test('Refresh fetches again', async () => {
  const seen = mockContacts(pageOf(1))
  const { user } = renderApp(path)
  await screen.findByRole('table')
  const before = seen.length
  await user.click(screen.getByRole('button', { name: t.refresh }))
  await waitFor(() => expect(seen.length).toBe(before + 1))
})

test('a failed load offers a retry', async () => {
  mockContacts(() => HttpResponse.json({}, { status: 500 }))
  renderApp(path)
  expect(await screen.findByText(t.loadFailed)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: strings.retry })).toBeInTheDocument()
})

test('a page that no longer exists offers a way back to page 1', async () => {
  const seen = mockContacts((q) =>
    q.get('page') === '1'
      ? pageOf(3)(q)
      : HttpResponse.json({ detail: 'Invalid page.' }, { status: 404 }),
  )
  const { user } = renderApp(`${path}?tab=contacts&page=9`)
  expect(await screen.findByText(t.pageGone)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: t.firstPage }))
  expect(await screen.findByRole('table')).toBeInTheDocument()
  expect(seen.at(-1)?.get('page')).toBe('1')
})

test.each(Object.entries(ALL_ROLES))('%s can open the contacts tab', async (_n, roles) => {
  mockContacts(pageOf(1))
  renderApp(path, roles)
  expect(await screen.findByRole('table', { name: t.tableLabel })).toBeInTheDocument()
})
