import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/api'
import { useRecording, useTranscript } from '../../api/queries'
import { Button } from '../../components/Button'
import { DateTime } from '../../components/DateTime'
import { inputClass } from '../../components/Field'
import { useToast } from '../../components/Toast'
import { formatDuration } from '../../lib/format'
import { strings } from '../../lib/strings'

const t = strings.attempt
const notFound = (e: unknown) => e instanceof ApiError && e.status === 404

const Notice = () => <p className="mb-2 text-xs text-muted">{t.auditNotice}</p>

// Splits text into plain and matching parts; the parts are rendered by React, so no HTML is built.
function split(text: string, needle: string): { text: string; match: boolean }[] {
  const n = needle.toLowerCase()
  if (!n) return [{ text, match: false }]
  const hay = text.toLowerCase()
  const parts: { text: string; match: boolean }[] = []
  let at = 0
  for (let i = hay.indexOf(n); i !== -1; i = hay.indexOf(n, at)) {
    if (i > at) parts.push({ text: text.slice(at, i), match: false })
    parts.push({ text: text.slice(i, i + n.length), match: true })
    at = i + n.length
  }
  if (at < text.length) parts.push({ text: text.slice(at), match: false })
  return parts
}

export function TranscriptPanel({ id }: { id: string }) {
  const toast = useToast()
  const q = useTranscript(id)
  const [search, setSearch] = useState('')
  const parts = useMemo(() => split(q.data?.content ?? '', search), [q.data, search])
  const matches = parts.filter((p) => p.match).length

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(q.data?.content ?? '')
      toast.success(t.copied)
    } catch {
      toast.error(t.copyFailed)
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">{t.transcript}</h2>
      <Notice />
      {!q.data && !notFound(q.error) && (
        <Button variant="secondary" disabled={q.isFetching} onClick={() => void q.refetch()}>
          {q.isFetching ? t.loadingTranscript : t.loadTranscript}
        </Button>
      )}
      {notFound(q.error) && <p className="text-sm text-muted">{t.noTranscript}</p>}
      {q.isError && !notFound(q.error) && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t.transcriptFailed}
        </p>
      )}
      {q.data && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {q.data.is_partial && (
              <span className="rounded-full border border-amber-700 px-2 py-0.5 text-xs text-amber-800 dark:border-amber-400 dark:text-amber-300">
                {t.partial}
              </span>
            )}
            <span className="text-muted">
              {t.updated} <DateTime iso={q.data.updated_at} />
            </span>
            <Button variant="secondary" onClick={() => void copy()}>
              {t.copy}
            </Button>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="search"
              aria-label={t.searchTranscript}
              placeholder={t.searchTranscript}
              autoComplete="off"
              spellCheck={false}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={`${inputClass} max-w-xs`}
            />
            {search && (
              <span role="status" className="text-sm text-muted">
                {t.matches(matches)}
              </span>
            )}
          </div>
          {/* Scrollable regions must be keyboard-focusable so the text can be scrolled without a mouse */}
          <div
            role="region"
            aria-label={t.transcriptRegion}
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
            tabIndex={0}
            className="max-h-96 overflow-y-auto rounded-md border border-border p-3 text-sm whitespace-pre-wrap"
          >
            {parts.map((p, i) =>
              p.match ? (
                <mark key={i} className="bg-yellow-300 text-black">
                  {p.text}
                </mark>
              ) : (
                <span key={i}>{p.text}</span>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Presigned URLs carry their own expiry: SigV4 gives a lifetime in seconds, the older SigV2 style an
// absolute epoch. Without either, assume the backend default of 5 minutes.
function expiresAt(url: string, fetchedAt: number): number {
  try {
    const params = new URL(url).searchParams
    const absolute = Number(params.get('Expires'))
    if (absolute > 0) return absolute * 1000
    const lifetime = Number(params.get('X-Amz-Expires'))
    if (lifetime > 0) return fetchedAt + lifetime * 1000
  } catch {
    // not a parseable URL: use the default below
  }
  return fetchedAt + 300_000
}

export function RecordingPanel({ id }: { id: string }) {
  const q = useRecording(id)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!q.data) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [q.data])

  const left = q.data
    ? Math.max(0, Math.ceil((expiresAt(q.data.url, q.dataUpdatedAt) - now) / 1000))
    : 0
  const expired = Boolean(q.data) && left === 0
  const reload = () => {
    setNow(Date.now())
    void q.refetch()
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">{t.recording}</h2>
      <Notice />
      {!q.data && !notFound(q.error) && (
        <Button variant="secondary" disabled={q.isFetching} onClick={reload}>
          {q.isFetching ? t.loadingRecording : t.loadRecording}
        </Button>
      )}
      {notFound(q.error) && <p className="text-sm text-muted">{t.noRecording}</p>}
      {q.isError && !notFound(q.error) && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t.recordingFailed}
        </p>
      )}
      {q.data && (
        <div className="space-y-2 text-sm">
          {expired ? (
            <p role="status">{t.expired}</p>
          ) : (
            // The transcript panel is the text alternative; a call recording has no caption track.
            // The URL is only ever used as the player source: never logged, stored or shown.
            // eslint-disable-next-line jsx-a11y/media-has-caption
            <audio
              controls
              preload="none"
              src={q.data.url}
              aria-label={t.audioLabel}
              className="w-full max-w-md"
            />
          )}
          <p className="text-muted">
            {q.data.duration_seconds !== null && (
              <>
                {t.recordingLength} {formatDuration(q.data.duration_seconds)} ·{' '}
              </>
            )}
            {!expired && <span>{t.expiresIn(left)}</span>}
          </p>
          {expired && (
            <Button variant="secondary" disabled={q.isFetching} onClick={reload}>
              {t.reloadRecording}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
