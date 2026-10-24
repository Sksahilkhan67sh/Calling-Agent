export const ADMIN = 'Admin'
export const MANAGER = 'Campaign Manager'
export const SALES = 'Sales/Follow-up'

export interface Me {
  id: number
  username: string
  roles: string[]
}

export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed'
export const CAMPAIGN_STATUSES: CampaignStatus[] = ['draft', 'active', 'paused', 'completed']

export interface Campaign {
  id: string
  name: string
  status: CampaignStatus
  contact_count: number
  created_at: string
  // Only present for Admin
  workflow_synced?: boolean
}
