import { useEffect, useState, type MutableRefObject, type ReactNode } from 'react'
import type { FieldValues, Path, UseFormReturn } from 'react-hook-form'
import { ApiError } from '../../api/api'
import { strings } from '../../lib/strings'
import { Button } from '../Button'
import { useToast } from '../Toast'

const t = strings.config

interface Props<V extends FieldValues> {
  form: UseFormReturn<V>
  readOnly: boolean
  save: (values: V) => Promise<unknown>
  // Server field name -> form field name
  serverFields: Record<string, Path<V>>
  // The page reads this when the person navigates away, to ask before discarding edits
  dirtyRef: MutableRefObject<boolean>
  children: ReactNode
}

export function ConfigForm<V extends FieldValues>({
  form,
  readOnly,
  save,
  serverFields,
  dirtyRef,
  children,
}: Props<V>) {
  const toast = useToast()
  const [formError, setFormError] = useState<string | null>(null)
  const { isDirty, isSubmitting } = form.formState

  useEffect(() => {
    dirtyRef.current = isDirty
    if (!isDirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
      dirtyRef.current = false
    }
  }, [isDirty, dirtyRef])

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null)
    try {
      await save(values)
      toast.success(t.saved)
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      let mapped = false
      for (const [server, messages] of Object.entries(e.fieldErrors)) {
        const field = serverFields[server]
        if (field && messages[0]) {
          form.setError(field, { message: messages[0] })
          mapped = true
        }
      }
      if (!mapped) setFormError(e.fieldErrors.non_field_errors?.[0] ?? e.message ?? t.saveFailed)
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="max-w-xl space-y-5">
      {readOnly && <p className="text-sm text-muted">{t.readOnly}</p>}
      {/* A disabled fieldset makes every control read-only for assistive tech too */}
      <fieldset disabled={readOnly || isSubmitting} className="min-w-0 space-y-5">
        {children}
      </fieldset>
      {formError && (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      )}
      {!readOnly && (
        <div className="flex gap-2">
          <Button type="submit" disabled={isSubmitting || !isDirty}>
            {isSubmitting ? t.saving : t.save}
          </Button>
          <Button
            variant="secondary"
            disabled={isSubmitting || !isDirty}
            onClick={() => form.reset()}
          >
            {t.reset}
          </Button>
        </div>
      )}
    </form>
  )
}
