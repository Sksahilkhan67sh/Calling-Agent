import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { isThrottled } from './throttle'
import type { AgentConfig, Campaign, CampaignStatus, Me, RetryPolicy } from './types'

// Retries are handled in api.ts (one GET retry on a dropped connection); nothing here retries.
// The cache lives in memory only and is cleared on logout.
export const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 10_000 }, mutations: { retry: false } },
  })

export const queryKeys = {
  me: ['me'] as const,
  campaigns: ['campaigns'] as const,
  campaign: (id: string) => ['campaigns', 'detail', id] as const,
  retryPolicy: (id: string) => ['campaigns', 'detail', id, 'retry-policy'] as const,
  agentConfig: (id: string) => ['campaigns', 'detail', id, 'agent-config'] as const,
  campaignList: (status: CampaignStatus | '') => ['campaigns', 'list', status || 'all'] as const,
}

// Poll only while the tab is visible and the server has not asked us to slow down.
export const pollEvery = (ms: number) => () =>
  document.visibilityState === 'visible' && !isThrottled() ? ms : (false as const)

export const fetchMe = (signal?: AbortSignal) => api<Me>('/v1/auth/me', { signal })

export function useCampaigns(status: CampaignStatus | '') {
  return useQuery({
    queryKey: queryKeys.campaignList(status),
    queryFn: ({ signal }) =>
      api<Campaign[]>(`/v1/campaigns${status ? `?status=${status}` : ''}`, { signal }),
    refetchInterval: pollEvery(30_000),
  })
}

export function useCreateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      name,
      file,
      retryPolicy,
      agentConfig,
    }: {
      name: string
      file: File
      // Admin only; sent as JSON strings inside the multipart body
      retryPolicy?: object | undefined
      agentConfig?: object | undefined
    }) => {
      const form = new FormData()
      form.append('name', name)
      form.append('contact_file', file)
      if (retryPolicy) form.append('retry_policy', JSON.stringify(retryPolicy))
      if (agentConfig) form.append('agent_config', JSON.stringify(agentConfig))
      return api<Campaign>('/v1/campaigns', { method: 'POST', form })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.campaigns }),
  })
}

export function useCampaign(id: string) {
  return useQuery({
    queryKey: queryKeys.campaign(id),
    queryFn: ({ signal }) => api<Campaign>(`/v1/campaigns/${id}`, { signal }),
    refetchInterval: pollEvery(30_000),
  })
}

export function useUpdateCampaignStatus(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (status: CampaignStatus) =>
      api<Campaign>(`/v1/campaigns/${id}`, { method: 'PATCH', json: { status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.campaigns }),
  })
}

export function useSyncWorkflow(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api<{ workflow_uuid: string }>(`/v1/campaigns/${id}/sync-workflow`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.campaign(id) }),
  })
}

// Config is edited by one Admin at a time; polling would overwrite their unsaved input.
export function useRetryPolicy(id: string) {
  return useQuery({
    queryKey: queryKeys.retryPolicy(id),
    queryFn: ({ signal }) => api<RetryPolicy>(`/v1/campaigns/${id}/retry-policy`, { signal }),
    refetchOnWindowFocus: false,
  })
}

export function useAgentConfig(id: string) {
  return useQuery({
    queryKey: queryKeys.agentConfig(id),
    queryFn: ({ signal }) => api<AgentConfig>(`/v1/campaigns/${id}/agent-config`, { signal }),
    refetchOnWindowFocus: false,
  })
}

// A saved config changes the rendered workflow, so the detail's workflow_synced flag is refetched.
export function useSaveRetryPolicy(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<RetryPolicy>) =>
      api<RetryPolicy>(`/v1/campaigns/${id}/retry-policy`, { method: 'PUT', json: body }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.retryPolicy(id), data)
      return qc.invalidateQueries({ queryKey: queryKeys.campaign(id), exact: true })
    },
  })
}

export function useSaveAgentConfig(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<AgentConfig>) =>
      api<AgentConfig>(`/v1/campaigns/${id}/agent-config`, { method: 'PUT', json: body }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.agentConfig(id), data)
      return qc.invalidateQueries({ queryKey: queryKeys.campaign(id), exact: true })
    },
  })
}
