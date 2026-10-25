import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/api'
import { useContact, useSuppressContact } from '../api/queries'
import { ADMIN, MANAGER } from '../api/types'
import { useHasRole } from '../auth/guards'
import { Button, buttonClass } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DateTime } from '../components/DateTime'
import { ErrorState } from '../components/ErrorState'
import { inputClass } from '../components/Field'
import { JsonValue } from '../components/JsonValue'
import { PhoneCell } from '../components/PhoneCell'
import { AttemptStateBadge, ContactStatusBadge } from '../components/StatusBadge'
import { useToast } from '../components/Toast'
import { formatDuration } from '../lib/format'
import { strings } from '../lib/strings'
import { isUuid } from '../lib/uuid'
import { NotFound } from './NotFound'

const t = strings.contact

export function Contact() {
  const { id } = useParams()
  return isUuid(id) ? <ContactView id={id} /> : <NotFound />
}

const seconds = (from: string | null, to: string | null) =>
  from && to ? Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / 1000)) : null

function ContactView({ id }: { id: string }) {
  const toast = useToast()
  const isAdmin = useHasRole(ADMIN)
  const isStaff = useHasRole(ADMIN, MANAGER)
  const query = useContact(id)
  const suppress = useSuppressContact(id)
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')

  if (query.isError) {
    const gone = query.error instanceof ApiError && query.error.status === 404
    return gone ? (
      <NotFound />
    ) : (
      <ErrorState error={query.error} message={t.loadFailed} onRetry={() => void query.refetch()} />
    )
  }
  const contact = query.data
  if (!contact)
    return (
      <p role="status" aria-busy="true" className="text-muted">
        {strings.loading}…
      </p>
    )

  const close = () => {
    setOpen(false)
    setReason('')
  }
  const confirmSuppress = async () => {
    try {
      await suppress.mutateAsync(reason.trim())
      toast.success(t.suppressDone)
      close()
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      toast.error(e.fieldErrors.reason?.[0] ?? t.suppressFailed)
    }
  }

  const fo = contact.final_output
  return (
    <section className="space-y-6">
      <div>
        <Link to={`/campaigns/${contact.campaign_id}`} className="text-sm text-primary underline">
          {t.backToCampaign}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{t.heading}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          <PhoneCell phone={contact.phone_number} />
          <ContactStatusBadge status={contact.status} />
          <span className="text-muted">{t.attempts(contact.attempt_count)}</span>
        </div>
      </div>

      {contact.suppression ? (
        <div
          role="status"
          className="rounded-md border border-red-700 p-3 text-sm dark:border-red-400"
        >
          <p className="font-medium">{t.suppressed}</p>
          <p className="whitespace-pre-wrap">{t.suppressedBody(contact.suppression.reason)}</p>
          <p className="text-muted">
            {t.suppressedMeta(contact.suppression.source)} ·{' '}
            <DateTime iso={contact.suppression.requested_at} />
          </p>
        </div>
      ) : (
        isAdmin && (
          <Button variant="danger" onClick={() => setOpen(true)}>
            {t.suppress}
          </Button>
        )
      )}

      <div>
        <h2 className="mb-2 text-lg font-semibold">{t.attemptsTitle}</h2>
        {contact.attempts.length === 0 ? (
          <p className="text-sm text-muted">{t.noAttempts}</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <caption className="sr-only">{t.attemptsTitle}</caption>
              <thead className="bg-card">
                <tr>
                  {[
                    t.colNumber,
                    t.colState,
                    t.colReason,
                    t.colConsent,
                    t.colStarted,
                    t.colEnded,
                    t.colDuration,
                  ].map((h) => (
                    <th key={h} scope="col" className="px-3 py-2">
                      {h}
                    </th>
                  ))}
                  {isStaff && (
                    <th scope="col" className="px-3 py-2">
                      <span className="sr-only">{t.viewAttempt}</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {contact.attempts.map((a) => {
                  const reasonKey = a.connection_failure_reason ?? a.disconnect_reason
                  const secs = seconds(a.started_at, a.ended_at)
                  return (
                    <tr key={a.id} className="border-t border-border">
                      <th scope="row" className="px-3 py-2 font-medium">
                        {a.attempt_number}
                      </th>
                      <td className="px-3 py-2">
                        <AttemptStateBadge state={a.state} />
                      </td>
                      <td className="px-3 py-2">
                        {reasonKey ? (strings.reasons[reasonKey] ?? reasonKey) : t.empty}
                      </td>
                      <td className="px-3 py-2">{a.recording_consent ?? t.empty}</td>
                      <td className="px-3 py-2">
                        {a.started_at ? <DateTime iso={a.started_at} /> : t.empty}
                      </td>
                      <td className="px-3 py-2">
                        {a.ended_at ? <DateTime iso={a.ended_at} /> : t.empty}
                      </td>
                      <td className="px-3 py-2">
                        {secs === null ? t.empty : formatDuration(secs)}
                      </td>
                      {isStaff && (
                        <td className="px-3 py-2">
                          <Link to={`/call-attempts/${a.id}`} className="text-primary underline">
                            {t.viewAttempt}
                          </Link>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-lg font-semibold">{t.finalOutput}</h2>
        {!fo ? (
          <p className="text-sm text-muted">{t.noResult}</p>
        ) : (
          <div className="space-y-4 rounded-md border border-border p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              {fo.transcript && <Chip>{t.hasTranscript}</Chip>}
              {fo.recording && <Chip>{t.hasRecording}</Chip>}
              {isStaff && fo.transcript && (
                <Link
                  to={`/call-attempts/${fo.transcript.attempt_id}`}
                  className={buttonClass('secondary')}
                >
                  {t.openTranscript}
                </Link>
              )}
              {isStaff && fo.recording && (
                <Link
                  to={`/call-attempts/${fo.recording.attempt_id}`}
                  className={buttonClass('secondary')}
                >
                  {t.openRecording}
                </Link>
              )}
            </div>
            {(
              [
                [t.summary, fo.call_summary],
                [t.feedback, fo.feedback],
                [t.interest, fo.interest_detection],
                [t.leadScore, fo.lead_score_summary],
              ] as const
            ).map(([title, value]) => (
              <div key={title}>
                <h3 className="font-medium">{title}</h3>
                <JsonValue value={value} />
              </div>
            ))}
            <p className="text-xs text-muted">
              {t.generated} <DateTime iso={fo.generated_at} />
            </p>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={open}
        title={t.suppressTitle}
        description={
          <>
            <p className="font-medium text-danger">{t.suppressWarning}</p>
            <label className="mt-3 block text-sm text-fg">
              {t.reason}
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                rows={3}
                autoComplete="off"
                className={`${inputClass} mt-1`}
              />
            </label>
            <p className="mt-1 text-xs text-muted">{t.reasonCount(reason.length)}</p>
          </>
        }
        confirmLabel={suppress.isPending ? t.suppressing : t.suppressConfirm}
        cancelLabel={strings.cancel}
        danger
        pending={suppress.isPending}
        onConfirm={() => void confirmSuppress()}
        onCancel={close}
      />
    </section>
  )
}

const Chip = ({ children }: { children: string }) => (
  <span className="rounded-full border border-border px-2 py-0.5 text-xs">{children}</span>
)
