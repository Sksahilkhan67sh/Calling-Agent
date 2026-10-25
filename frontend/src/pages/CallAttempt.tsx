import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/api'
import { useAttempt, useDisconnectEvents } from '../api/queries'
import { DateTime } from '../components/DateTime'
import { ErrorState } from '../components/ErrorState'
import { AttemptStateBadge } from '../components/StatusBadge'
import { formatDuration } from '../lib/format'
import { strings } from '../lib/strings'
import { isUuid } from '../lib/uuid'
import { NotFound } from './NotFound'
import { RecordingPanel, TranscriptPanel } from './attempt/MediaPanels'

const t = strings.attempt

export function CallAttempt() {
  const { id } = useParams()
  return isUuid(id) ? <AttemptView id={id} /> : <NotFound />
}

function AttemptView({ id }: { id: string }) {
  const query = useAttempt(id)
  const events = useDisconnectEvents(id)

  if (query.isError) {
    const gone = query.error instanceof ApiError && query.error.status === 404
    return gone ? (
      <NotFound />
    ) : (
      <ErrorState error={query.error} message={t.loadFailed} onRetry={() => void query.refetch()} />
    )
  }
  const a = query.data
  if (!a)
    return (
      <p role="status" aria-busy="true" className="text-muted">
        {strings.loading}…
      </p>
    )

  const secs =
    a.started_at && a.ended_at
      ? Math.max(0, Math.round((Date.parse(a.ended_at) - Date.parse(a.started_at)) / 1000))
      : null
  const reason = (key: string | null) =>
    key ? (strings.reasons[key] ?? key) : strings.contact.empty
  const details: [string, React.ReactNode][] = [
    [t.number, a.attempt_number],
    [t.state, <AttemptStateBadge key="s" state={a.state} />],
    [t.failureReason, reason(a.connection_failure_reason)],
    [t.disconnectReason, reason(a.disconnect_reason)],
    [t.consent, a.recording_consent ?? strings.contact.empty],
    [t.started, a.started_at ? <DateTime key="a" iso={a.started_at} /> : strings.contact.empty],
    [t.ended, a.ended_at ? <DateTime key="b" iso={a.ended_at} /> : strings.contact.empty],
    [t.duration, secs === null ? strings.contact.empty : formatDuration(secs)],
  ]

  return (
    <section className="space-y-6">
      <div>
        <Link to={`/contacts/${a.contact_id}`} className="text-sm text-primary underline">
          {t.backToContact}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{t.heading}</h1>
      </div>

      <dl className="grid max-w-xl gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
        {details.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      <div>
        <h2 className="mb-2 text-lg font-semibold">{t.events}</h2>
        {events.isPending ? (
          <p role="status" aria-busy="true" className="text-muted">
            {strings.loading}…
          </p>
        ) : events.isError ? (
          <ErrorState
            error={events.error}
            message={t.eventsFailed}
            onRetry={() => void events.refetch()}
          />
        ) : events.data.length === 0 ? (
          <p className="text-sm text-muted">{t.noEvents}</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border text-sm">
            {events.data.map((e) => (
              <li key={e.id} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                <span className="font-medium">{reason(e.reason)}</span>
                <span className="text-muted">
                  <DateTime iso={e.occurred_at} /> ·{' '}
                  {e.retry_approved ? t.retryApproved : t.retryNotApproved}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <TranscriptPanel id={id} />
      <RecordingPanel id={id} />
    </section>
  )
}
