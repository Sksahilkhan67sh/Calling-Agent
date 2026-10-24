import type { CampaignStatus } from '../api/types'

// Mirrors the server's TRANSITIONS table; the server stays the authority.
export const NEXT_STATUSES: Record<CampaignStatus, CampaignStatus[]> = {
  draft: ['active'],
  active: ['paused', 'completed'],
  paused: ['active', 'completed'],
  completed: [],
}

export type StatusAction = 'activate' | 'resume' | 'pause' | 'complete'

export function statusAction(from: CampaignStatus, to: CampaignStatus): StatusAction {
  if (to === 'completed') return 'complete'
  if (to === 'paused') return 'pause'
  return from === 'paused' ? 'resume' : 'activate'
}
