import { screen, waitFor, within } from '@testing-library/react'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { strings } from '../src/lib/strings'
import { server } from './server'
import { ALL_ROLES, renderApp } from './utils'

const t = strings.contact
const ID = '11111111-1111-4111-8111-111111111111'
const CID = '6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d'
const AID = '22222222-2222-4222-8222-222222222222'
const path = `/contacts/${ID}`

const attempt = (over: Record<string, unknown> = {}) => ({
  id: AID,
  contact_id: ID,
  attempt_number: 1,
  state: 'EndedNormally',
  connection_failure_reason: null,
  disconnect_reason: null,
  recording_consent: 'granted',
  started_at: '2026-10-20T08:30:00Z',
  ended_at: '2026-10-20T08:32:05Z',
  ...over,
})
const detail = (over: Record<string, unknown> = {}) => ({
  id: ID,
  campaign_id: CID,
  phone_number: '+919876547678',
  status: 'Completed',
  attempt_count: 1,
  created_at: '2026-10-20T08:00:00Z',
  suppression: null,
  attempts: [attempt()],
  final_output: null,
  ...over,
})
const finalOutput = (over: Record<string, unknown> = {}) => ({
  id: 'f1',
  contact_id: ID,
  source_attempt_id: AID,
  transcript: { attempt_id: AID, is_partial: false, updated_at: '2026-10-20T08:33:00Z' },
  recording: { attempt_id: AID, duration_seconds: 125 },
  feedback: { sentiment: 'positive', notes: ['likes pricing', 'wants a demo'] },
  interest_detection: 'High interest',
  lead_score_summary: { score: 82, tier: { name: 'Hot' } },
  call_summary: 'Customer wants a demo next week.',
  generated_at: '2026-10-20T08:35:00Z',
  ...over,
})
const mockContact = (d: Record<string, unknown> = detail()) =>
  server.use(http.get(`*/v1/contacts/${ID}`, () => HttpResponse.json(d)))

describe('route', () => {
  test('a malformed id is not found', async () => {
    renderApp('/contacts/nope')
    expect(await screen.findByText(strings.notFound.title)).toBeInTheDocument()
  })

  test('a 404 is not found', async () => {
    server.use(http.get(`*/v1/contacts/${ID}`, () => HttpResponse.json({}, { status: 404 })))
    renderApp(path)
    expect(await screen.findByText(strings.notFound.title)).toBeInTheDocument()
  })

  test('a server error offers a retry', async () => {
    server.use(http.get(`*/v1/contacts/${ID}`, () => HttpResponse.json({}, { status: 500 })))
    renderApp(path)
    expect(await screen.findByText(t.loadFailed)).toBeInTheDocument()
  })
})

describe('header and attempts', () => {
  test('masked phone with reveal, status, attempt count, back link; no axe violations', async () => {
    mockContact()
    const { user, container } = renderApp(path)
    expect(await screen.findByRole('heading', { name: t.heading })).toBeInTheDocument()
    expect(screen.getByTestId('phone')).toHaveTextContent('+91•••••7678')
    expect(container.innerHTML).not.toContain('9876547678')
    expect(screen.getByText(t.attempts(1))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.backToCampaign })).toHaveAttribute(
      'href',
      `/campaigns/${CID}`,
    )
    await user.click(screen.getByRole('button', { name: strings.phone.reveal }))
    expect(screen.getByTestId('phone')).toHaveTextContent('+919876547678')
    expect(await axe(container)).toHaveNoViolations()
  })

  test('the page never puts the number in the document title or URL', async () => {
    mockContact()
    const { router } = renderApp(path)
    await screen.findByRole('heading', { name: t.heading })
    expect(document.title).not.toContain('9876547678')
    expect(router.state.location.pathname + router.state.location.search).not.toContain(
      '9876547678',
    )
  })

  test('attempts table shows state, reason, consent, times and computed duration', async () => {
    mockContact(
      detail({
        attempts: [
          attempt(),
          attempt({
            id: '33333333-3333-4333-8333-333333333333',
            attempt_number: 2,
            state: 'FailedToConnect',
            connection_failure_reason: 'no_answer',
            recording_consent: null,
            ended_at: null,
          }),
          attempt({
            id: '44444444-4444-4444-8444-444444444444',
            attempt_number: 3,
            state: 'DroppedMidCall',
            disconnect_reason: 'network_problem',
          }),
        ],
        attempt_count: 3,
      }),
    )
    renderApp(path)
    const table = await screen.findByRole('table', { name: t.attemptsTitle })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows[0]!).getByText('Ended normally')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('2 min 5 s')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('granted')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Failed to connect')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('No answer')).toBeInTheDocument()
    expect(within(rows[2]!).getByText('Network problem')).toBeInTheDocument()
  })

  test('no attempts yet', async () => {
    mockContact(detail({ attempts: [], attempt_count: 0 }))
    renderApp(path)
    expect(await screen.findByText(t.noAttempts)).toBeInTheDocument()
  })

  test('staff get a View attempt link per row; Sales do not', async () => {
    mockContact()
    renderApp(path, ALL_ROLES.manager)
    expect(await screen.findByRole('link', { name: t.viewAttempt })).toHaveAttribute(
      'href',
      `/call-attempts/${AID}`,
    )
  })

  test('Sales get no View attempt link', async () => {
    mockContact()
    renderApp(path, ALL_ROLES.sales)
    await screen.findByRole('table', { name: t.attemptsTitle })
    expect(screen.queryByRole('link', { name: t.viewAttempt })).toBeNull()
  })
})

describe('final output', () => {
  test('no result yet is shown calmly', async () => {
    mockContact()
    renderApp(path)
    expect(await screen.findByText(t.noResult)).toBeInTheDocument()
  })

  test('summary, unknown JSON shapes and chips render as plain text', async () => {
    mockContact(detail({ final_output: finalOutput() }))
    renderApp(path)
    expect(await screen.findByText('Customer wants a demo next week.')).toBeInTheDocument()
    expect(screen.getByText('likes pricing')).toBeInTheDocument()
    expect(screen.getByText('High interest')).toBeInTheDocument()
    expect(screen.getByText('82')).toBeInTheDocument()
    expect(screen.getByText('Hot')).toBeInTheDocument()
    expect(screen.getByText(t.hasTranscript)).toBeInTheDocument()
    expect(screen.getByText(t.hasRecording)).toBeInTheDocument()
  })

  test('a call_summary that is JSON rather than text still renders', async () => {
    mockContact(
      detail({
        final_output: finalOutput({
          call_summary: { headline: 'Wants a demo', next_steps: ['Send deck'] },
        }),
      }),
    )
    renderApp(path)
    expect(await screen.findByText('Wants a demo')).toBeInTheDocument()
    expect(screen.getByText('Send deck')).toBeInTheDocument()
  })

  test('markup in server text is shown as text, not parsed', async () => {
    mockContact(
      detail({
        final_output: finalOutput({
          call_summary: '<img src=x onerror=alert(1)>',
          feedback: '<b>bold</b>',
        }),
      }),
    )
    const { container } = renderApp(path)
    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  test('odd shapes (null, numbers, deep nesting, empty) do not crash', async () => {
    mockContact(
      detail({
        final_output: finalOutput({
          feedback: null,
          interest_detection: 7,
          lead_score_summary: { a: { b: { c: { d: { e: 'deep' } } } } },
          call_summary: null,
        }),
      }),
    )
    renderApp(path)
    expect(await screen.findByText(t.finalOutput)).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  test('staff get Open transcript / Open recording; Sales see the text but no buttons', async () => {
    mockContact(detail({ final_output: finalOutput() }))
    const staff = renderApp(path, ALL_ROLES.admin)
    expect(await screen.findByRole('link', { name: t.openTranscript })).toHaveAttribute(
      'href',
      `/call-attempts/${AID}`,
    )
    expect(screen.getByRole('link', { name: t.openRecording })).toBeInTheDocument()
    staff.unmount()

    renderApp(path, ALL_ROLES.sales)
    expect(await screen.findByText('Customer wants a demo next week.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openTranscript })).toBeNull()
    expect(screen.queryByRole('link', { name: t.openRecording })).toBeNull()
  })

  test('no transcript or recording chips when neither exists', async () => {
    mockContact(detail({ final_output: finalOutput({ transcript: null, recording: null }) }))
    renderApp(path)
    await screen.findByText('Customer wants a demo next week.')
    expect(screen.queryByText(t.hasTranscript)).toBeNull()
    expect(screen.queryByText(t.hasRecording)).toBeNull()
  })
})

describe('suppression', () => {
  test('a suppressed contact shows the banner and no Suppress button, even for Admin', async () => {
    mockContact(
      detail({
        suppression: {
          contact_id: ID,
          reason: 'Asked to stop',
          source: 'manual_api',
          requested_at: '2026-10-21T08:00:00Z',
        },
      }),
    )
    renderApp(path)
    expect(await screen.findByText(t.suppressed)).toBeInTheDocument()
    expect(screen.getByText(t.suppressedBody('Asked to stop'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.suppress })).toBeNull()
  })

  test.each([
    ['Manager', ALL_ROLES.manager],
    ['Sales', ALL_ROLES.sales],
  ])('%s never sees the Suppress button', async (_n, roles) => {
    mockContact()
    renderApp(path, roles)
    await screen.findByRole('heading', { name: t.heading })
    expect(screen.queryByRole('button', { name: t.suppress })).toBeNull()
  })

  test('the dialog warns it is permanent, counts the reason and sends it on confirm (201)', async () => {
    mockContact()
    let body: unknown
    server.use(
      http.post(`*/v1/contacts/${ID}/suppress`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          {
            contact_id: ID,
            reason: 'DNC request',
            source: 'manual_api',
            requested_at: '2026-10-24T08:00:00Z',
          },
          { status: 201 },
        )
      }),
    )
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.suppress }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(t.suppressWarning)).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText(t.reason), 'DNC request')
    expect(within(dialog).getByText(t.reasonCount(11))).toBeInTheDocument()
    // After success the page refetches and now shows the suppression
    mockContact(
      detail({
        suppression: {
          contact_id: ID,
          reason: 'DNC request',
          source: 'manual_api',
          requested_at: '2026-10-24T08:00:00Z',
        },
      }),
    )
    await user.click(within(dialog).getByRole('button', { name: t.suppressConfirm }))
    expect(await screen.findByText(t.suppressDone)).toBeInTheDocument()
    expect(body).toEqual({ reason: 'DNC request' })
    expect(await screen.findByText(t.suppressed)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.suppress })).toBeNull()
  })

  test('200 (already suppressed) is handled like a success', async () => {
    mockContact()
    server.use(
      http.post(`*/v1/contacts/${ID}/suppress`, () =>
        HttpResponse.json(
          {
            contact_id: ID,
            reason: '',
            source: 'manual_api',
            requested_at: '2026-10-24T08:00:00Z',
          },
          { status: 200 },
        ),
      ),
    )
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.suppress }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: t.suppressConfirm }))
    expect(await screen.findByText(t.suppressDone)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  })

  test('cancel sends nothing; a failure keeps the dialog open and says so', async () => {
    mockContact()
    let calls = 0
    server.use(
      http.post(`*/v1/contacts/${ID}/suppress`, () => {
        calls++
        return HttpResponse.json({ detail: 'nope' }, { status: 500 })
      }),
    )
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.suppress }))
    let dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: strings.cancel }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(calls).toBe(0)

    await user.click(screen.getByRole('button', { name: t.suppress }))
    dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: t.suppressConfirm }))
    expect(await screen.findByText(t.suppressFailed)).toBeInTheDocument()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  test('the reason is capped at 500 characters', async () => {
    mockContact()
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.suppress }))
    expect(await screen.findByLabelText(t.reason)).toHaveAttribute('maxlength', '500')
  })
})
