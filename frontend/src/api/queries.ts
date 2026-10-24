import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { isThrottled } from './throttle'
import type { Campaign, CampaignStatus, Me } from './types'

// Retries are handled in api.ts (one GET retry on a dropped connection); nothing here retries.
// The cache lives in memory only and is cleared on logout.
export const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 10_000 }, mutations: { retry: false } },
  })

export const queryKeys = {
  me: ['me'] as const,
  campaigns: ['campaigns'] as const,
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
    mutationFn: ({ name, file }: { name: string; file: File }) => {
      const form = new FormData()
      form.append('name', name)
      form.append('contact_file', file)
      return api<Campaign>('/v1/campaigns', { method: 'POST', form })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.campaigns }),
  })
}
