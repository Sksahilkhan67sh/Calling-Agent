import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCampaigns } from '../api/queries'
import { ADMIN, CAMPAIGN_STATUSES, type CampaignStatus, MANAGER } from '../api/types'
import { useHasRole } from '../auth/guards'
import { Button, buttonClass } from '../components/Button'
import { DateTime } from '../components/DateTime'
import { ErrorState } from '../components/ErrorState'
import { inputClass } from '../components/Field'
import { CampaignStatusBadge } from '../components/StatusBadge'
import { strings } from '../lib/strings'

const t = strings.campaigns

function Skeleton() {
  return (
    <div aria-busy="true" role="status" className="space-y-2">
      <span className="sr-only">{strings.loading}</span>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-10 animate-pulse rounded-md bg-card" />
      ))}
    </div>
  )
}

export function Campaigns() {
  const canCreate = useHasRole(ADMIN, MANAGER)
  const [status, setStatus] = useState<CampaignStatus | ''>('')
  const [search, setSearch] = useState('')
  const q = useCampaigns(status)

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (q.data ?? [])
      .filter((c) => c.name.toLowerCase().includes(needle))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
  }, [q.data, search])

  const filtered = status !== '' || search.trim() !== ''

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t.title}</h1>
        <div className="flex gap-2">
          <Button variant="secondary" disabled={q.isFetching} onClick={() => void q.refetch()}>
            {q.isFetching ? t.refreshing : t.refresh}
          </Button>
          {canCreate && (
            <Link to="/campaigns/new" className={buttonClass()}>
              {t.new}
            </Link>
          )}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <label className="text-sm">
          <span className="mr-2">{t.filterStatus}</span>
          <select
            className={`${inputClass} w-auto`}
            value={status}
            onChange={(e) => setStatus(e.target.value as CampaignStatus | '')}
          >
            <option value="">{t.all}</option>
            {CAMPAIGN_STATUSES.map((s) => (
              <option key={s} value={s}>
                {strings.campaignStatus[s]}
              </option>
            ))}
          </select>
        </label>
        <input
          type="search"
          aria-label={t.search}
          placeholder={t.search}
          autoComplete="off"
          className={`${inputClass} max-w-xs`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {q.isPending ? (
        <Skeleton />
      ) : q.isError ? (
        <ErrorState error={q.error} message={t.loadFailed} onRetry={() => void q.refetch()} />
      ) : rows.length === 0 ? (
        <div className="rounded-md border border-border p-8 text-center">
          <p className="font-medium">{filtered ? t.noMatch : canCreate ? t.empty : t.emptySales}</p>
          {!filtered && canCreate && (
            <>
              <p className="mt-1 text-sm text-muted">{t.emptyHint}</p>
              <Link to="/campaigns/new" className={`${buttonClass()} mt-4`}>
                {t.new}
              </Link>
            </>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <caption className="sr-only">{t.tableLabel}</caption>
            <thead className="bg-card">
              <tr>
                <th scope="col" className="px-3 py-2">
                  {t.colName}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t.colStatus}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t.colContacts}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t.colCreated}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="relative border-t border-border hover:bg-card">
                  <th scope="row" className="px-3 py-2 font-medium">
                    <Link to={`/campaigns/${c.id}`} className="after:absolute after:inset-0">
                      {c.name}
                    </Link>
                  </th>
                  <td className="px-3 py-2">
                    <CampaignStatusBadge status={c.status} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{c.contact_count}</td>
                  <td className="px-3 py-2">
                    <DateTime iso={c.created_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
