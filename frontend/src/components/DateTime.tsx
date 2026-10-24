import { formatDateTime, formatRelative } from '../lib/format'

// Local time for reading, UTC ISO in the tooltip, relative time only as secondary text.
export function DateTime({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={iso}>
      {formatDateTime(iso)} <span className="text-muted">({formatRelative(iso)})</span>
    </time>
  )
}
