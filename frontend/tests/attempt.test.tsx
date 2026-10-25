import { act, screen, waitFor } from '@testing-library/react'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { strings } from '../src/lib/strings'
import { server } from './server'
import { ALL_ROLES, renderApp } from './utils'

const t = strings.attempt
const ID = '22222222-2222-4222-8222-222222222222'
const CONTACT = '11111111-1111-4111-8111-111111111111'
const path = `/call-attempts/${ID}`

const attempt = {
  id: ID,
  contact_id: CONTACT,
  attempt_number: 2,
  state: 'DroppedMidCall',
  connection_failure_reason: null,
  disconnect_reason: 'network_problem',
  recording_consent: 'granted',
  started_at: '2026-10-20T08:30:00Z',
  ended_at: '2026-10-20T08:31:30Z',
}
const events = [
  {
    id: 'e1',
    attempt_id: ID,
    reason: 'network_problem',
    occurred_at: '2026-10-20T08:31:30Z',
    retry_approved: true,
  },
  {
    id: 'e2',
    attempt_id: ID,
    reason: 'customer_hangup',
    occurred_at: '2026-10-20T08:31:40Z',
    retry_approved: false,
  },
]
const transcript = {
  attempt_id: ID,
  is_partial: true,
  content: 'Agent: Hello there\nCustomer: hello, I like the plan\nAgent: Great <b>news</b>',
  updated_at: '2026-10-20T08:33:00Z',
}
const URL_ = 'https://storage.example.test/rec.mp3?X-Amz-Signature=abc123&X-Amz-Expires=5'

function mock(extra: { transcript?: () => Response; recording?: () => Response } = {}) {
  const calls = { transcript: 0, recording: 0 }
  server.use(
    http.get(`*/v1/call-attempts/${ID}`, () => HttpResponse.json(attempt)),
    http.get(`*/v1/call-attempts/${ID}/disconnect-events`, () => HttpResponse.json(events)),
    http.get(`*/v1/call-attempts/${ID}/transcript`, () => {
      calls.transcript++
      return extra.transcript ? extra.transcript() : HttpResponse.json(transcript)
    }),
    http.get(`*/v1/call-attempts/${ID}/recording`, () => {
      calls.recording++
      return extra.recording
        ? extra.recording()
        : HttpResponse.json({ attempt_id: ID, url: URL_, duration_seconds: 125 })
    }),
  )
  return calls
}

describe('route and roles', () => {
  test('a malformed id is not found', async () => {
    renderApp('/call-attempts/nope')
    expect(await screen.findByText(strings.notFound.title)).toBeInTheDocument()
  })

  test('Sales are sent to the forbidden page and nothing is requested', async () => {
    renderApp(path, ALL_ROLES.sales)
    expect(await screen.findByText(strings.forbidden.title)).toBeInTheDocument()
  })

  test('a 404 is not found; a server error offers a retry', async () => {
    server.use(http.get(`*/v1/call-attempts/${ID}`, () => HttpResponse.json({}, { status: 404 })))
    const first = renderApp(path)
    expect(await screen.findByText(strings.notFound.title)).toBeInTheDocument()
    first.unmount()
    server.use(http.get(`*/v1/call-attempts/${ID}`, () => HttpResponse.json({}, { status: 500 })))
    renderApp(path)
    expect(await screen.findByText(t.loadFailed)).toBeInTheDocument()
  })
})

describe('details and disconnect events', () => {
  test('shows all fields, a back link to the contact and the events; no axe violations', async () => {
    mock()
    const { container } = renderApp(path, ALL_ROLES.manager)
    expect(await screen.findByRole('heading', { name: t.heading })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.backToContact })).toHaveAttribute(
      'href',
      `/contacts/${CONTACT}`,
    )
    expect(screen.getByText('Dropped mid-call')).toBeInTheDocument()
    expect(screen.getByText('1 min 30 s')).toBeInTheDocument()
    expect(screen.getByText('granted')).toBeInTheDocument()
    expect(await screen.findByText(new RegExp(t.retryApproved))).toBeInTheDocument()
    expect(screen.getByText(new RegExp(t.retryNotApproved))).toBeInTheDocument()
    expect(screen.getByText('Customer hung up')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  test('no events, and a failing events request, are both explained', async () => {
    mock()
    server.use(http.get(`*/v1/call-attempts/${ID}/disconnect-events`, () => HttpResponse.json([])))
    const first = renderApp(path)
    expect(await screen.findByText(t.noEvents)).toBeInTheDocument()
    first.unmount()
    server.use(
      http.get(`*/v1/call-attempts/${ID}/disconnect-events`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    )
    renderApp(path)
    expect(await screen.findByText(t.eventsFailed)).toBeInTheDocument()
  })
})

describe('transcript', () => {
  test('is not requested until the button is clicked, and the audit notice is shown first', async () => {
    const calls = mock()
    const { user } = renderApp(path)
    await screen.findByRole('button', { name: t.loadTranscript })
    expect(screen.getAllByText(t.auditNotice)).toHaveLength(2) // transcript and recording panels
    await new Promise((r) => setTimeout(r, 50))
    expect(calls.transcript).toBe(0)
    await user.click(screen.getByRole('button', { name: t.loadTranscript }))
    expect(await screen.findByRole('region', { name: t.transcriptRegion })).toHaveTextContent(
      'Hello there',
    )
    expect(calls.transcript).toBe(1)
    expect(screen.getByText(t.partial)).toBeInTheDocument()
  })

  test('search highlights matches safely and counts them; markup stays text', async () => {
    mock()
    const { user, container } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadTranscript }))
    const region = await screen.findByRole('region', { name: t.transcriptRegion })
    expect(region).toHaveTextContent('Great <b>news</b>')
    expect(container.querySelector('b')).toBeNull()
    await user.type(screen.getByLabelText(t.searchTranscript), 'HELLO')
    expect(screen.getByText(t.matches(2))).toBeInTheDocument()
    const marks = region.querySelectorAll('mark')
    expect([...marks].map((m) => m.textContent)).toEqual(['Hello', 'hello'])
    // Searching for markup characters matches them literally
    await user.clear(screen.getByLabelText(t.searchTranscript))
    await user.type(screen.getByLabelText(t.searchTranscript), '<b>')
    expect(screen.getByText(t.matches(1))).toBeInTheDocument()
    expect(region.querySelector('mark')?.textContent).toBe('<b>')
    expect(container.querySelector('b')).toBeNull()
  })

  test('Copy transcript writes the text to the clipboard', async () => {
    mock()
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadTranscript }))
    await screen.findByRole('region', { name: t.transcriptRegion })
    const write = vi.spyOn(navigator.clipboard, 'writeText')
    await user.click(screen.getByRole('button', { name: t.copy }))
    expect(write).toHaveBeenCalledWith(transcript.content)
    expect(await screen.findByText(t.copied)).toBeInTheDocument()
  })

  test('a 404 says there is no transcript and removes the button', async () => {
    mock({ transcript: () => HttpResponse.json({ detail: 'Not found.' }, { status: 404 }) })
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadTranscript }))
    expect(await screen.findByText(t.noTranscript)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.loadTranscript })).toBeNull()
  })

  test('a server error is reported and loading can be tried again', async () => {
    let fail = true
    const calls = mock({
      transcript: () =>
        fail ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(transcript),
    })
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadTranscript }))
    expect(await screen.findByText(t.transcriptFailed)).toBeInTheDocument()
    fail = false
    await user.click(screen.getByRole('button', { name: t.loadTranscript }))
    expect(await screen.findByRole('region', { name: t.transcriptRegion })).toBeInTheDocument()
    expect(calls.transcript).toBe(2)
  })

  test('the text is dropped when the page is left and is not fetched again on return', async () => {
    const calls = mock()
    const { user, router } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadTranscript }))
    await screen.findByRole('region', { name: t.transcriptRegion })
    await act(() => router.navigate('/forbidden'))
    // gcTime is 0: the cache entry is removed as soon as the observer is gone
    await new Promise((r) => setTimeout(r, 50))
    await act(() => router.navigate(path))
    expect(await screen.findByRole('button', { name: t.loadTranscript })).toBeInTheDocument()
    expect(screen.queryByText(/Hello there/)).toBeNull()
    expect(calls.transcript).toBe(1)
  })
})

describe('recording', () => {
  afterEach(() => vi.useRealTimers())

  test('is not requested until clicked; the URL is only the player source', async () => {
    const calls = mock()
    const { user, container } = renderApp(path)
    await screen.findByRole('button', { name: t.loadRecording })
    await new Promise((r) => setTimeout(r, 50))
    expect(calls.recording).toBe(0)
    await user.click(screen.getByRole('button', { name: t.loadRecording }))
    const audio = await screen.findByLabelText(t.audioLabel)
    expect(audio).toHaveAttribute('src', URL_)
    expect(calls.recording).toBe(1)
    expect(screen.getByText(/2 min 5 s/)).toBeInTheDocument()
    // The URL appears nowhere as text
    expect(container.textContent).not.toContain('storage.example.test')
    expect(container.textContent).not.toContain('abc123')
  })

  test('counts down, unloads the player at expiry and Reload fetches a fresh link', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    const calls = mock()
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadRecording }))
    await screen.findByLabelText(t.audioLabel)
    expect(screen.getByText(t.expiresIn(5))).toBeInTheDocument()
    act(() => void vi.advanceTimersByTime(2000))
    expect(screen.getByText(t.expiresIn(3))).toBeInTheDocument()
    act(() => void vi.advanceTimersByTime(4000))
    expect(screen.getByText(t.expired)).toBeInTheDocument()
    expect(screen.queryByLabelText(t.audioLabel)).toBeNull()
    await user.click(screen.getByRole('button', { name: t.reloadRecording }))
    expect(await screen.findByLabelText(t.audioLabel)).toBeInTheDocument()
    expect(calls.recording).toBe(2)
    expect(screen.getByText(t.expiresIn(5))).toBeInTheDocument()
  })

  test('an absolute Expires (SigV2 style URL) sets the countdown', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-10-25T10:00:00Z'))
    const expires = Date.parse('2026-10-25T10:00:00Z') / 1000 + 4
    mock({
      recording: () =>
        HttpResponse.json({
          attempt_id: ID,
          url: `https://storage.example.test/rec.mp3?AWSAccessKeyId=k&Signature=s&Expires=${expires}`,
          duration_seconds: 10,
        }),
    })
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadRecording }))
    await screen.findByLabelText(t.audioLabel)
    expect(screen.getByText(t.expiresIn(4))).toBeInTheDocument()
    act(() => void vi.advanceTimersByTime(5000))
    expect(screen.getByText(t.expired)).toBeInTheDocument()
  })

  test('a 404 explains why there is no recording', async () => {
    mock({ recording: () => HttpResponse.json({ detail: 'Not found.' }, { status: 404 }) })
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadRecording }))
    expect(await screen.findByText(t.noRecording)).toBeInTheDocument()
    expect(screen.queryByLabelText(t.audioLabel)).toBeNull()
  })

  test('a server error is reported and the button stays', async () => {
    mock({ recording: () => HttpResponse.json({}, { status: 500 }) })
    const { user } = renderApp(path)
    await user.click(await screen.findByRole('button', { name: t.loadRecording }))
    expect(await screen.findByText(t.recordingFailed)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: t.loadRecording })).toBeEnabled())
  })
})
