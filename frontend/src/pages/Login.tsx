import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { ApiError } from '../api/api'
import { useAuth } from '../auth/AuthProvider'
import { Button } from '../components/Button'
import { Field, inputClass } from '../components/Field'
import { safeNext } from '../lib/safeRedirect'
import { strings } from '../lib/strings'

const t = strings.login
const schema = z.object({
  username: z.string().trim().min(1, t.required),
  password: z.string().min(1, t.required),
  mfa_code: z.string().regex(/^(\d{6})?$/, t.mfaInvalid),
})
type Values = z.infer<typeof schema>

export function Login() {
  const { status, login } = useAuth()
  const [params] = useSearchParams()
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    resetField,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '', mfa_code: '' },
  })

  if (status === 'loading') {
    return (
      <p role="status" aria-busy="true" className="p-8 text-muted">
        {strings.loading}…
      </p>
    )
  }
  if (status === 'authenticated') return <Navigate to={safeNext(params.get('next'))} replace />

  const onSubmit = handleSubmit(async ({ username, password, mfa_code }) => {
    setFormError(null)
    try {
      await login({ username, password, ...(mfa_code && { mfa_code }) })
    } catch (e) {
      // Same message for a wrong password and a wrong code, exactly like the server.
      const status = e instanceof ApiError ? e.status : 0
      setFormError(
        status === 401
          ? t.invalid
          : status === 429
            ? t.tooMany
            : e instanceof ApiError
              ? e.message
              : strings.api.generic,
      )
      resetField('password')
      resetField('mfa_code')
    }
  })

  const trackCaps = (e: React.KeyboardEvent) => setCapsLock(e.getModifierState('CapsLock'))

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-4">
      <h1 className="mb-1 text-2xl font-semibold">{strings.appName}</h1>
      <p className="mb-6 text-muted">{t.title}</p>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field label={t.username} error={errors.username?.message}>
          {(p) => (
            <input
              {...p}
              {...register('username')}
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              className={inputClass}
            />
          )}
        </Field>
        <Field label={t.password} error={errors.password?.message}>
          {(p) => (
            <div className="flex gap-2">
              <input
                {...p}
                {...register('password')}
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                onKeyDown={trackCaps}
                onKeyUp={trackCaps}
                className={inputClass}
              />
              <Button
                variant="secondary"
                aria-pressed={showPassword}
                onClick={() => setShowPassword((s) => !s)}
              >
                {showPassword ? t.hide : t.show}
              </Button>
            </div>
          )}
        </Field>
        {capsLock && (
          <p role="status" className="text-sm text-muted">
            {t.capsLock}
          </p>
        )}
        <Field label={t.mfa} error={errors.mfa_code?.message} help={t.mfaHelp}>
          {(p) => (
            <input
              {...p}
              {...register('mfa_code')}
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              spellCheck={false}
              className={inputClass}
            />
          )}
        </Field>
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? t.submitting : t.submit}
        </Button>
      </form>
    </main>
  )
}
