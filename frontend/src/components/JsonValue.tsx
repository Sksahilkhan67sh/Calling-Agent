import { strings } from '../lib/strings'

const MAX_DEPTH = 4
const label = (key: string) => key.replace(/_/g, ' ')

// Server JSON has no guaranteed shape, so everything is rendered as plain text through React
// (never as HTML). Deep or odd values fall back to their JSON text.
export function JsonValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined || value === '')
    return <span className="text-muted">{strings.contact.empty}</span>
  if (typeof value === 'string') return <span className="whitespace-pre-wrap">{value}</span>
  if (typeof value === 'number' || typeof value === 'boolean') return <span>{String(value)}</span>
  if (depth >= MAX_DEPTH)
    return <span className="whitespace-pre-wrap">{JSON.stringify(value)}</span>
  if (Array.isArray(value))
    return (
      <ul className="list-disc pl-5">
        {value.map((v, i) => (
          <li key={i}>
            <JsonValue value={v} depth={depth + 1} />
          </li>
        ))}
      </ul>
    )
  if (typeof value === 'object')
    return (
      <dl className="space-y-1">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs font-medium text-muted capitalize">{label(k)}</dt>
            <dd>
              <JsonValue value={v} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    )
  return <span className="whitespace-pre-wrap">{String(value)}</span>
}
