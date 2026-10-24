import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react'

type Kind = 'success' | 'error'
interface Item {
  id: number
  kind: Kind
  message: string
}

interface Toasts {
  success: (message: string) => void
  error: (message: string) => void
}

const Ctx = createContext<Toasts | null>(null)
let nextId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([])
  const dismiss = useCallback((id: number) => setItems((l) => l.filter((i) => i.id !== id)), [])
  const push = useCallback(
    (kind: Kind, message: string) => {
      const id = nextId++
      setItems((l) => [...l, { id, kind, message }])
      setTimeout(() => dismiss(id), kind === 'error' ? 8000 : 5000)
    },
    [dismiss],
  )
  const api = useMemo<Toasts>(
    () => ({ success: (m) => push('success', m), error: (m) => push('error', m) }),
    [push],
  )
  return (
    <Ctx.Provider value={api}>
      {children}
      {/* Live region stays mounted so announcements are reliable */}
      <div
        role="status"
        aria-live="polite"
        className="fixed right-4 bottom-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
      >
        {items.map((i) => (
          <div
            key={i.id}
            className={`flex items-start justify-between gap-3 rounded-md border bg-bg p-3 text-sm shadow-lg ${i.kind === 'error' ? 'border-danger' : 'border-border'}`}
          >
            <span>
              <span className="font-semibold">{i.kind === 'error' ? 'Error: ' : 'Success: '}</span>
              {i.message}
            </span>
            <button
              type="button"
              aria-label="Dismiss"
              className="rounded px-1 text-muted hover:text-fg"
              onClick={() => dismiss(i.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export function useToast(): Toasts {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}
