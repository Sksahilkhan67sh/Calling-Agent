import { type ReactNode, useId } from 'react'

interface Props {
  label: string
  error?: string | undefined
  help?: ReactNode
  children: (props: {
    id: string
    'aria-invalid': boolean
    'aria-describedby': string | undefined
  }) => ReactNode
}

export const inputClass =
  'w-full rounded-md border border-border bg-bg px-3 py-2 text-sm placeholder:text-muted'

// Wires label, hint and error to the control so screen readers announce them together.
export function Field({ label, error, help, children }: Props) {
  const id = useId()
  const describedBy = [help ? `${id}-help` : '', error ? `${id}-error` : '']
    .filter(Boolean)
    .join(' ')
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {children({
        id,
        'aria-invalid': Boolean(error),
        'aria-describedby': describedBy || undefined,
      })}
      {help && (
        <p id={`${id}-help`} className="mt-1 text-xs text-muted">
          {help}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
