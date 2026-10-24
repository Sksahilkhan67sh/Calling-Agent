import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { api, setAuthLostHandler } from '../api/api'
import { fetchMe, queryKeys } from '../api/queries'
import { resetThrottle } from '../api/throttle'
import type { Me } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { strings } from '../lib/strings'
import { useIdleTimeout } from './useIdleTimeout'

export interface Credentials {
  username: string
  password: string
  mfa_code?: string
}

interface AuthValue {
  user: Me | null
  status: 'loading' | 'authenticated' | 'anonymous'
  login: (credentials: Credentials) => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthValue | null>(null)
const CHANNEL = 'calling-agent-auth'
const LOGGED_OUT = 'logged-out' // the only message ever sent between tabs: no data

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [signedOut, setSignedOut] = useState(false)
  const [expired, setExpired] = useState(false)
  const channel = useRef<BroadcastChannel | null>(null)

  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => fetchMe(signal),
    enabled: !signedOut,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  })
  const user = signedOut ? null : (me.data ?? null)
  const status = signedOut
    ? 'anonymous'
    : me.isPending
      ? 'loading'
      : user
        ? 'authenticated'
        : 'anonymous'

  // Signing out flips this flag; RequireAuth then unmounts every page (and redirects to /login).
  // Only after that is the cache cleared, otherwise a still-mounted query would refetch and refill it.
  const clearSession = useCallback(() => {
    setExpired(false)
    setSignedOut(true)
  }, [])
  useEffect(() => {
    if (!signedOut) return
    qc.clear()
    resetThrottle()
  }, [signedOut, qc])

  const logout = useCallback(async () => {
    const server = api('/v1/auth/logout', { method: 'POST', skipRefresh: true }).catch(
      () => undefined,
    )
    channel.current?.postMessage(LOGGED_OUT)
    clearSession()
    await server
  }, [clearSession])

  const login = useCallback(
    async (credentials: Credentials) => {
      await api('/v1/auth/token', { method: 'POST', json: credentials, skipRefresh: true })
      setSignedOut(false)
      await qc.fetchQuery({
        queryKey: queryKeys.me,
        queryFn: ({ signal }) => fetchMe(signal),
        staleTime: 0,
      })
    },
    [qc],
  )

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const ch = new BroadcastChannel(CHANNEL)
    channel.current = ch
    ch.onmessage = (e) => {
      if (e.data === LOGGED_OUT) clearSession()
    }
    return () => {
      ch.close()
      channel.current = null
    }
  }, [clearSession])

  const hadUser = useRef(false)
  useEffect(() => {
    hadUser.current = Boolean(user)
  }, [user])
  useEffect(() => {
    // Refresh failed mid-session. A failed /me on first load just means "not signed in".
    setAuthLostHandler(() => {
      if (hadUser.current) setExpired(true)
    })
    return () => setAuthLostHandler(undefined)
  }, [])

  const idle = useIdleTimeout(status === 'authenticated', logout)

  const value = useMemo(
    () => ({ user, status, login, logout }) as AuthValue,
    [user, status, login, logout],
  )

  return (
    <Ctx.Provider value={value}>
      {children}
      <ConfirmDialog
        open={idle.secondsLeft !== null}
        title={strings.idle.title}
        description={strings.idle.body(idle.secondsLeft ?? 0)}
        confirmLabel={strings.idle.stay}
        cancelLabel={strings.idle.signOut}
        dismissable={false}
        onConfirm={() => {
          idle.stay()
          void qc.invalidateQueries({ queryKey: queryKeys.me })
        }}
        onCancel={() => void logout()}
      />
      <ConfirmDialog
        open={expired}
        title={strings.expired.title}
        description={strings.expired.body}
        confirmLabel={strings.expired.action}
        dismissable={false}
        onConfirm={() => {
          channel.current?.postMessage(LOGGED_OUT)
          clearSession()
        }}
      />
    </Ctx.Provider>
  )
}

export function useAuth(): AuthValue {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
