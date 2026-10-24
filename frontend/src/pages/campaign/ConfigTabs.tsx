import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, type MutableRefObject } from 'react'
import { useForm } from 'react-hook-form'
import {
  useAgentConfig,
  useRetryPolicy,
  useSaveAgentConfig,
  useSaveRetryPolicy,
} from '../../api/queries'
import { ErrorState } from '../../components/ErrorState'
import {
  AgentConfigFields,
  agentDefaults,
  agentFromServer,
  agentSchema,
  agentServerFields,
  agentToPayload,
  type AgentValues,
} from '../../components/config/AgentConfigFields'
import { ConfigForm } from '../../components/config/ConfigForm'
import {
  RetryPolicyFields,
  retryDefaults,
  retryFromServer,
  retrySchema,
  retryServerFields,
  retryToPayload,
  type RetryValues,
} from '../../components/config/RetryPolicyFields'
import { strings } from '../../lib/strings'

interface Props {
  id: string
  canEdit: boolean
  dirtyRef: MutableRefObject<boolean>
}

const Loading = () => (
  <p role="status" aria-busy="true" className="text-muted">
    {strings.loading}…
  </p>
)

export function RetryPolicyTab({ id, canEdit, dirtyRef }: Props) {
  const query = useRetryPolicy(id)
  const save = useSaveRetryPolicy(id)
  const values = useMemo(
    () => (query.data ? retryFromServer(query.data) : retryDefaults),
    [query.data],
  )
  const form = useForm<RetryValues>({ resolver: zodResolver(retrySchema), values })

  if (query.isError)
    return (
      <ErrorState
        error={query.error}
        message={strings.config.loadFailed}
        onRetry={() => void query.refetch()}
      />
    )
  if (!query.data) return <Loading />
  return (
    <ConfigForm
      form={form}
      readOnly={!canEdit}
      dirtyRef={dirtyRef}
      serverFields={retryServerFields}
      save={async (v) => form.reset(retryFromServer(await save.mutateAsync(retryToPayload(v))))}
    >
      <RetryPolicyFields form={form} />
    </ConfigForm>
  )
}

export function AgentConfigTab({ id, canEdit, dirtyRef }: Props) {
  const query = useAgentConfig(id)
  const save = useSaveAgentConfig(id)
  const values = useMemo(
    () => (query.data ? agentFromServer(query.data) : agentDefaults),
    [query.data],
  )
  const form = useForm<AgentValues>({ resolver: zodResolver(agentSchema), values })

  if (query.isError)
    return (
      <ErrorState
        error={query.error}
        message={strings.config.loadFailed}
        onRetry={() => void query.refetch()}
      />
    )
  if (!query.data) return <Loading />
  return (
    <ConfigForm
      form={form}
      readOnly={!canEdit}
      dirtyRef={dirtyRef}
      serverFields={agentServerFields}
      save={async (v) => form.reset(agentFromServer(await save.mutateAsync(agentToPayload(v))))}
    >
      <AgentConfigFields form={form} version={query.data.prompt_template_version} />
    </ConfigForm>
  )
}
