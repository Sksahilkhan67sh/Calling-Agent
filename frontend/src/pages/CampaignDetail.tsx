import * as Tabs from '@radix-ui/react-tabs'
import { useRef, useState } from 'react'
import { useBlocker, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/api'
import { useCampaign, useSyncWorkflow, useUpdateCampaignStatus } from '../api/queries'
import { ADMIN, MANAGER, type CampaignStatus } from '../api/types'
import { useHasRole } from '../auth/guards'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DateTime } from '../components/DateTime'
import { ErrorState } from '../components/ErrorState'
import { CampaignStatusBadge } from '../components/StatusBadge'
import { useToast } from '../components/Toast'
import { formatRelative } from '../lib/format'
import { strings } from '../lib/strings'
import { NEXT_STATUSES, statusAction } from '../lib/transitions'
import { isUuid } from '../lib/uuid'
import { NotFound } from './NotFound'
import { AgentConfigTab, RetryPolicyTab } from './campaign/ConfigTabs'
import { ContactsTab } from './campaign/ContactsTab'

const t = strings.campaignDetail
const TABS = ['contacts', 'retry', 'agent'] as const
type Tab = (typeof TABS)[number]

export function CampaignDetail() {
  const { id } = useParams()
  return isUuid(id) ? <Detail id={id} /> : <NotFound />
}

function Detail({ id }: { id: string }) {
  const toast = useToast()
  const isAdmin = useHasRole(ADMIN)
  const canManage = useHasRole(ADMIN, MANAGER)
  const query = useCampaign(id)
  const setStatus = useUpdateCampaignStatus(id)
  const sync = useSyncWorkflow(id)
  const [confirm, setConfirm] = useState<CampaignStatus | 'sync' | null>(null)
  const [syncedAt, setSyncedAt] = useState<number | null>(null)
  const [params, setParams] = useSearchParams()
  // Set by whichever tab form has unsaved edits
  const dirtyRef = useRef(false)
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirtyRef.current &&
      currentLocation.pathname + currentLocation.search !==
        nextLocation.pathname + nextLocation.search,
  )

  if (query.isError) {
    const gone = query.error instanceof ApiError && query.error.status === 404
    return gone ? (
      <NotFound />
    ) : (
      <ErrorState error={query.error} message={t.loadFailed} onRetry={() => void query.refetch()} />
    )
  }
  const campaign = query.data
  if (!campaign)
    return (
      <p role="status" aria-busy="true" className="text-muted">
        {strings.loading}…
      </p>
    )

  const requested = params.get('tab')
  const visibleTabs = TABS.filter((x) => x === 'contacts' || canManage)
  const tab: Tab = visibleTabs.find((x) => x === requested) ?? 'contacts'
  const stale = isAdmin && campaign.workflow_synced === false
  const busy = setStatus.isPending || sync.isPending

  const runStatus = async (to: CampaignStatus) => {
    try {
      await setStatus.mutateAsync(to)
      toast.success(t.statusDone(strings.campaignStatus[to] ?? to))
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      toast.error(e.fieldErrors.status?.[0] ?? e.message ?? t.statusFailed)
    } finally {
      setConfirm(null)
    }
  }

  const runSync = async () => {
    try {
      const { workflow_uuid } = await sync.mutateAsync()
      setSyncedAt(Date.now())
      toast.success(t.syncDone(workflow_uuid))
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      toast.error(e.status === 502 ? t.syncFailed : e.message)
    } finally {
      setConfirm(null)
    }
  }

  const pendingAction =
    confirm && confirm !== 'sync' ? statusAction(campaign.status, confirm) : null

  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{campaign.name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            <CampaignStatusBadge status={campaign.status} />
            <span>{t.contactCount(campaign.contact_count)}</span>
            <span>
              {t.created} <DateTime iso={campaign.created_at} />
            </span>
          </p>
        </div>
        {canManage && (
          <div className="flex flex-wrap gap-2">
            {NEXT_STATUSES[campaign.status].map((to) => {
              const action = statusAction(campaign.status, to)
              return (
                <Button
                  key={to}
                  variant={action === 'complete' ? 'danger' : 'primary'}
                  disabled={busy}
                  onClick={() => setConfirm(to)}
                >
                  {t.action[action]}
                </Button>
              )
            })}
            {isAdmin && (
              <Button variant="secondary" disabled={busy} onClick={() => setConfirm('sync')}>
                {sync.isPending ? t.syncing : t.sync}
              </Button>
            )}
          </div>
        )}
      </div>

      {stale && (
        <div
          role="status"
          className="mt-4 rounded-md border border-amber-700 p-3 text-sm dark:border-amber-400"
        >
          <p className="font-medium">{t.staleBanner}</p>
          <p className="text-muted">{t.staleBody}</p>
        </div>
      )}
      {syncedAt !== null && (
        <p className="mt-2 text-xs text-muted">
          {t.lastSync(formatRelative(new Date(syncedAt).toISOString()))}
        </p>
      )}

      <Tabs.Root
        value={tab}
        onValueChange={(v) => setParams({ tab: v }, { replace: true })}
        className="mt-6"
      >
        <Tabs.List aria-label={t.tabs} className="mb-4 flex gap-1 border-b border-border">
          {visibleTabs.map((x) => (
            <Tabs.Trigger
              key={x}
              value={x}
              className="-mb-px border-b-2 border-transparent px-4 py-2 text-sm data-[state=active]:border-primary data-[state=active]:font-medium"
            >
              {x === 'contacts' ? t.tabContacts : x === 'retry' ? t.retry : t.agent}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="contacts">
          <ContactsTab campaignId={id} />
        </Tabs.Content>
        {canManage && (
          <>
            <Tabs.Content value="retry">
              <RetryPolicyTab id={id} canEdit={isAdmin} dirtyRef={dirtyRef} />
            </Tabs.Content>
            <Tabs.Content value="agent">
              <AgentConfigTab id={id} canEdit={isAdmin} dirtyRef={dirtyRef} />
            </Tabs.Content>
          </>
        )}
      </Tabs.Root>

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm === 'sync'
            ? t.syncConfirmTitle
            : pendingAction
              ? t.confirm[pendingAction].title
              : ''
        }
        description={
          confirm === 'sync' ? (
            t.syncConfirmBody
          ) : pendingAction ? (
            <>
              <p>{t.confirm[pendingAction].body}</p>
              {pendingAction === 'activate' && stale && (
                <p className="mt-2 font-medium text-danger">{t.unsyncedWarning}</p>
              )}
            </>
          ) : null
        }
        confirmLabel={confirm === 'sync' ? t.sync : pendingAction ? t.action[pendingAction] : ''}
        cancelLabel={strings.cancel}
        danger={pendingAction === 'complete'}
        pending={busy}
        onConfirm={() => void (confirm === 'sync' ? runSync() : confirm && runStatus(confirm))}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={blocker.state === 'blocked'}
        title={t.unsavedTitle}
        description={t.unsavedBody}
        confirmLabel={t.unsavedLeave}
        cancelLabel={t.unsavedStay}
        danger
        onConfirm={() => blocker.state === 'blocked' && blocker.proceed()}
        onCancel={() => blocker.state === 'blocked' && blocker.reset()}
      />
    </section>
  )
}
