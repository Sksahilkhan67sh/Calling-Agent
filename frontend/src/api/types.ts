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

export const NEVER_CONNECTED_REASONS = [
  'no_answer',
  'busy',
  'invalid_number',
  'rejected',
  'network_error',
  'provider_error',
] as const
export const MID_CALL_REASONS = [
  'technical_issue',
  'network_problem',
  'provider_error',
  'ai_error',
  'unknown',
  'customer_hangup',
] as const
export const ENTITY_FIELDS = [
  'interest_level',
  'objection',
  'follow_up_preference',
  'decision_maker_status',
  'free_text_feedback',
] as const

export interface RetryPolicy {
  id: string
  campaign_id: string
  max_retries: number
  retry_spacing_seconds: number[]
  never_connected_rules: Record<(typeof NEVER_CONNECTED_REASONS)[number], boolean>
  mid_call_rules: Record<(typeof MID_CALL_REASONS)[number], boolean>
  // "HH:MM:SS" with no timezone: shown exactly as stored, never converted
  window_start: string
  window_end: string
}

export interface AgentConfig {
  id: string
  campaign_id: string
  persona_tone: string
  script_skeleton: string[]
  required_entity_fields: (typeof ENTITY_FIELDS)[number][]
  escalation_contact_method: string
  prompt_template_version: string
  model_config_uuid: string | null
}
