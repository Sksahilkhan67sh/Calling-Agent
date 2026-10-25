import { strings } from '../lib/strings'

const tones: Record<string, string> = {
  draft: 'border-border text-muted',
  active: 'border-green-700 text-green-800 dark:border-green-400 dark:text-green-300',
  paused: 'border-amber-700 text-amber-800 dark:border-amber-400 dark:text-amber-300',
  completed: 'border-blue-700 text-blue-800 dark:border-blue-400 dark:text-blue-300',
}

const good = 'border-green-700 text-green-800 dark:border-green-400 dark:text-green-300'
const warn = 'border-amber-700 text-amber-800 dark:border-amber-400 dark:text-amber-300'
const bad = 'border-red-700 text-red-800 dark:border-red-400 dark:text-red-300'
const info = 'border-blue-700 text-blue-800 dark:border-blue-400 dark:text-blue-300'
const quiet = 'border-border text-muted'
const contactTones: Record<string, string> = {
  Pending: quiet,
  Dialing: warn,
  InConversation: good,
  Disconnected: bad,
  RetryScheduled: warn,
  Reconnecting: warn,
  Completed: good,
  CompletedPartial: info,
  Closed: quiet,
}
const attemptTones: Record<string, string> = {
  Initiated: quiet,
  Connected: info,
  FailedToConnect: bad,
  DroppedMidCall: bad,
  EndedNormally: good,
}

const badge = (tone: string | undefined, label: string) => (
  <span
    className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${tone ?? quiet}`}
  >
    {label}
  </span>
)

export const ContactStatusBadge = ({ status }: { status: string }) =>
  badge(contactTones[status], strings.contactStatus[status] ?? status)

export const AttemptStateBadge = ({ state }: { state: string }) =>
  badge(attemptTones[state], strings.attemptState[state] ?? state)

// Colour is never the only signal: the label is always shown. Unknown values fall back to the raw string.
export function CampaignStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${tones[status] ?? 'border-border text-muted'}`}
    >
      {strings.campaignStatus[status] ?? status}
    </span>
  )
}
