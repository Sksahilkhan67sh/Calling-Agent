import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { strings } from '../lib/strings'
import { Forbidden } from '../pages/Forbidden'
import { useAuth } from './AuthProvider'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') {
    return (
      <div role="status" aria-busy="true" className="p-8 text-muted">
        {strings.loading}…
      </div>
    )
  }
  if (status === 'anonymous') {
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    )
  }
  return children
}

// UX only: the server decides. A 403 from the API is handled separately where data is loaded.
export function RequireRole({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { user } = useAuth()
  return user?.roles.some((r) => roles.includes(r)) ? children : <Forbidden />
}

export function useHasRole(...roles: string[]): boolean {
  const { user } = useAuth()
  return Boolean(user?.roles.some((r) => roles.includes(r)))
}
