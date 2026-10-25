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

export const CONTACT_STATUSES = [
  'Pending',
  'Dialing',
  'InConversation',
  'Disconnected',
  'RetryScheduled',
  'Reconnecting',
  'Completed',
  'CompletedPartial',
  'Closed',
] as const
export type ContactStatus = (typeof CONTACT_STATUSES)[number]

export interface Contact {
  id: string
  campaign_id: string
  // Full number as returned by the API: only ever rendered through maskPhone / PhoneCell
  phone_number: string
  status: ContactStatus
  attempt_count: number
  created_at: string
}

export interface ContactPage {
  total: number
  page: number
  items: Contact[]
}

export interface Suppression {
  contact_id: string
  reason: string
  source: string
  requested_at: string
}

export type AttemptState =
  'Initiated' | 'Connected' | 'FailedToConnect' | 'DroppedMidCall' | 'EndedNormally'

export interface CallAttempt {
  id: string
  contact_id: string
  attempt_number: number
  state: AttemptState
  connection_failure_reason: string | null
  disconnect_reason: string | null
  recording_consent: string | null
  started_at: string | null
  ended_at: string | null
}

export interface FinalOutput {
  id: string
  contact_id: string
  source_attempt_id: string | null
  transcript: { attempt_id: string; is_partial: boolean; updated_at: string } | null
  recording: { attempt_id: string; duration_seconds: number | null } | null
  // JSON of unknown shape: rendered defensively
  feedback: unknown
  interest_detection: unknown
  lead_score_summary: unknown
  call_summary: unknown
  generated_at: string
}

export interface ContactDetail extends Contact {
  suppression: Suppression | null
  attempts: CallAttempt[]
  final_output: FinalOutput | null
}

export interface DisconnectEvent {
  id: string
  attempt_id: string
  reason: string
  occurred_at: string
  retry_approved: boolean
}

export interface Transcript {
  attempt_id: string
  is_partial: boolean
  content: string
  updated_at: string
}

export interface Recording {
  attempt_id: string
  url: string
  duration_seconds: number | null
}
