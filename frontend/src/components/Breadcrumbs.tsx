import { Link, useMatches } from 'react-router-dom'
import { strings } from '../lib/strings'

export interface CrumbHandle {
  crumb?: string
}

export function Breadcrumbs() {
  const crumbs = useMatches().filter((m) => (m.handle as CrumbHandle | undefined)?.crumb)
  if (crumbs.length === 0) return null
  return (
    <nav aria-label={strings.breadcrumb.label} className="mb-4 text-sm text-muted">
      <ol className="flex flex-wrap gap-1">
        {crumbs.map((m, i) => {
          const label = (m.handle as CrumbHandle).crumb
          const last = i === crumbs.length - 1
          return (
            <li key={m.pathname} className="flex gap-1">
              {last ? (
                <span aria-current="page" className="text-fg">
                  {label}
                </span>
              ) : (
                <Link to={m.pathname} className="underline">
                  {label}
                </Link>
              )}
              {!last && <span aria-hidden>/</span>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
