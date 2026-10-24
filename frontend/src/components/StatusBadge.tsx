import { strings } from '../lib/strings'

const tones: Record<string, string> = {
  draft: 'border-border text-muted',
  active: 'border-green-700 text-green-800 dark:border-green-400 dark:text-green-300',
  paused: 'border-amber-700 text-amber-800 dark:border-amber-400 dark:text-amber-300',
  completed: 'border-blue-700 text-blue-800 dark:border-blue-400 dark:text-blue-300',
}

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
