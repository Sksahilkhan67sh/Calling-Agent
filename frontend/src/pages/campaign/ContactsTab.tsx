import { Link, useSearchParams } from 'react-router-dom'
import { useContacts } from '../../api/queries'
import { ApiError } from '../../api/api'
import { CONTACT_STATUSES } from '../../api/types'
import { Button } from '../../components/Button'
import { DateTime } from '../../components/DateTime'
import { ErrorState } from '../../components/ErrorState'
import { inputClass } from '../../components/Field'
import { PhoneCell } from '../../components/PhoneCell'
import { ContactStatusBadge } from '../../components/StatusBadge'
import { strings } from '../../lib/strings'

const t = strings.contacts
const PAGE_SIZES = [25, 50, 100, 200]

// URL params are untrusted input: anything unexpected falls back to the default.
const positiveInt = (v: string | null, fallback: number) => {
  const n = Number(v)
  return Number.isInteger(n) && n > 0 ? n : fallback
}

export function ContactsTab({ campaignId }: { campaignId: string }) {
  const [params, setParams] = useSearchParams()
  const rawStatus = params.get('status')
  const status = CONTACT_STATUSES.find((s) => s === rawStatus) ?? ''
  const size = positiveInt(params.get('size'), 50)
  const pageSize = PAGE_SIZES.includes(size) ? size : 50
  const page = positiveInt(params.get('page'), 1)
  const q = useContacts(campaignId, { status, page, pageSize })

  const update = (changes: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(changes)) {
          if (v === null || v === '') next.delete(k)
          else next.set(k, v)
        }
        return next
      },
      { replace: true },
    )

  const total = q.data?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  const goto = (p: number) => update({ page: p === 1 ? null : String(p) })

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap gap-3">
          <label className="text-sm">
            <span className="mr-2">{t.status}</span>
            <select
              className={`${inputClass} w-auto`}
              value={status}
              onChange={(e) => update({ status: e.target.value, page: null })}
            >
              <option value="">{t.all}</option>
              {CONTACT_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {strings.contactStatus[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mr-2">{t.pageSize}</span>
            <select
              className={`${inputClass} w-auto`}
              value={pageSize}
              onChange={(e) =>
                update({ size: e.target.value === '50' ? null : e.target.value, page: null })
              }
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
        <Button variant="secondary" disabled={q.isFetching} onClick={() => void q.refetch()}>
          {q.isFetching ? t.refreshing : t.refresh}
        </Button>
      </div>

      {q.isPending ? (
        <p role="status" aria-busy="true" className="text-muted">
          {strings.loading}…
        </p>
      ) : q.isError ? (
        q.error instanceof ApiError && q.error.status === 404 && page > 1 ? (
          <div role="alert" className="rounded-md border border-border p-4">
            <p>{t.pageGone}</p>
            <Button variant="secondary" className="mt-3" onClick={() => goto(1)}>
              {t.firstPage}
            </Button>
          </div>
        ) : (
          <ErrorState error={q.error} message={t.loadFailed} onRetry={() => void q.refetch()} />
        )
      ) : q.data.items.length === 0 ? (
        <div className="rounded-md border border-border p-8 text-center">
          <p className="font-medium">{status ? t.noMatch : t.empty}</p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <caption className="sr-only">{t.tableLabel}</caption>
              <thead className="bg-card">
                <tr>
                  <th scope="col" className="px-3 py-2">
                    {t.colPhone}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t.colStatus}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    {t.colAttempts}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t.colCreated}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    <span className="sr-only">{t.view}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((c) => (
                  <tr key={c.id} className="relative border-t border-border hover:bg-card">
                    <td className="px-3 py-2">
                      <PhoneCell phone={c.phone_number} />
                    </td>
                    <td className="px-3 py-2">
                      <ContactStatusBadge status={c.status} />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.attempt_count}</td>
                    <td className="px-3 py-2">
                      <DateTime iso={c.created_at} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Link
                        to={`/contacts/${c.id}`}
                        className="text-primary underline after:absolute after:inset-0"
                      >
                        {t.view}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav
            aria-label={t.pagination}
            className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
          >
            <p aria-live="polite">{t.range(from, to, total)}</p>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page <= 1} onClick={() => goto(1)}>
                {t.firstPage}
              </Button>
              <Button variant="secondary" disabled={page <= 1} onClick={() => goto(page - 1)}>
                {t.prevPage}
              </Button>
              <Button
                variant="secondary"
                disabled={page >= lastPage}
                onClick={() => goto(page + 1)}
              >
                {t.nextPage}
              </Button>
              <Button
                variant="secondary"
                disabled={page >= lastPage}
                onClick={() => goto(lastPage)}
              >
                {t.lastPage}
              </Button>
            </div>
          </nav>
        </>
      )}
    </div>
  )
}
