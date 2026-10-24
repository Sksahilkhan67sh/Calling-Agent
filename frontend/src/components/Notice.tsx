import type { ReactNode } from 'react'

export function Notice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="mx-auto max-w-md py-16 text-center">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <div className="mt-3 text-muted">{children}</div>
    </section>
  )
}
