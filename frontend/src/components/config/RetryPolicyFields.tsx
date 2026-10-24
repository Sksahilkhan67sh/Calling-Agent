import { z } from 'zod'
import { useWatch, type Path, type UseFormReturn } from 'react-hook-form'
import { Field, inputClass } from '../Field'
import { formatDuration } from '../../lib/format'
import { strings } from '../../lib/strings'
import { MID_CALL_REASONS, NEVER_CONNECTED_REASONS, type RetryPolicy } from '../../api/types'

const t = strings.retryPolicy
const num = (message: string) => z.number({ error: message }).int(message).min(0, message)
const rules = <K extends readonly string[]>(keys: K) =>
  z.object(Object.fromEntries(keys.map((k) => [k, z.boolean()])) as Record<K[number], z.ZodBoolean>)

export const retrySchema = z
  .object({
    max_retries: num(strings.config.invalidNumber).max(10, strings.config.invalidNumber),
    spacing: z.array(num(strings.config.invalidNumber)),
    never_connected_rules: rules(NEVER_CONNECTED_REASONS),
    mid_call_rules: rules(MID_CALL_REASONS),
    window_start: z.string().min(1, strings.config.required),
    window_end: z.string().min(1, strings.config.required),
  })
  .refine((v) => v.window_start < v.window_end, {
    path: ['window_end'],
    message: t.windowOrder,
  })
export type RetryValues = z.input<typeof retrySchema>

// Defaults mirror the backend model defaults; a saved policy replaces them.
export const retryDefaults: RetryValues = {
  max_retries: 2,
  spacing: [30, 600],
  never_connected_rules: {
    no_answer: true,
    busy: true,
    invalid_number: false,
    rejected: false,
    network_error: true,
    provider_error: true,
  },
  mid_call_rules: {
    technical_issue: true,
    network_problem: true,
    provider_error: true,
    ai_error: true,
    unknown: true,
    customer_hangup: false,
  },
  window_start: '10:00',
  window_end: '18:00',
}

export const retryFromServer = (p: RetryPolicy): RetryValues => ({
  max_retries: p.max_retries,
  spacing: p.retry_spacing_seconds,
  never_connected_rules: p.never_connected_rules,
  mid_call_rules: p.mid_call_rules,
  window_start: p.window_start.slice(0, 5),
  window_end: p.window_end.slice(0, 5),
})

export const retryToPayload = (v: RetryValues) => ({
  max_retries: v.max_retries,
  retry_spacing_seconds: v.spacing,
  never_connected_rules: v.never_connected_rules,
  mid_call_rules: v.mid_call_rules,
  window_start: v.window_start,
  window_end: v.window_end,
})

// Server field names -> form field names, for mapping 400 responses onto inputs.
export const retryServerFields: Record<string, keyof RetryValues> = {
  max_retries: 'max_retries',
  retry_spacing_seconds: 'spacing',
  never_connected_rules: 'never_connected_rules',
  mid_call_rules: 'mid_call_rules',
  window_start: 'window_start',
  window_end: 'window_end',
}

export function RetryPolicyFields({ form }: { form: UseFormReturn<RetryValues> }) {
  const {
    register,
    getValues,
    setValue,
    formState: { errors },
  } = form
  const resize = (count: number) => {
    if (!Number.isInteger(count) || count < 0 || count > 10) return
    const cur = getValues('spacing')
    const last = cur[cur.length - 1] ?? 600
    setValue(
      'spacing',
      Array.from({ length: count }, (_, i) => cur[i] ?? last),
      { shouldDirty: true },
    )
  }
  const spacing = useWatch({ control: form.control, name: 'spacing' })
  const spacingError = errors.spacing?.root?.message ?? errors.spacing?.message

  return (
    <div className="space-y-5">
      <Field label={t.maxRetries} help={t.maxRetriesHelp} error={errors.max_retries?.message}>
        {(p) => (
          <input
            {...p}
            {...register('max_retries', {
              valueAsNumber: true,
              onChange: (e: { target: { value: string } }) =>
                e.target.value !== '' && resize(Number(e.target.value)),
            })}
            type="number"
            min={0}
            max={10}
            className={`${inputClass} max-w-32`}
          />
        )}
      </Field>

      {spacing.map((seconds, i) => (
        <Field
          key={i}
          label={t.spacing(i + 1)}
          help={`${t.spacingHelp} ${formatDuration(seconds)}`}
          error={errors.spacing?.[i]?.message}
        >
          {(p) => (
            <input
              {...p}
              {...register(`spacing.${i}`, { valueAsNumber: true })}
              type="number"
              min={0}
              className={`${inputClass} max-w-32`}
            />
          )}
        </Field>
      ))}
      {spacingError && (
        <p role="alert" className="text-sm text-danger">
          {spacingError}
        </p>
      )}

      <RuleGroup
        legend={t.neverConnected}
        keys={NEVER_CONNECTED_REASONS}
        name="never_connected_rules"
        form={form}
      />
      <RuleGroup legend={t.midCall} keys={MID_CALL_REASONS} name="mid_call_rules" form={form} />

      <fieldset>
        <legend className="mb-1 text-sm font-medium">{t.window}</legend>
        <p className="mb-2 text-xs text-muted">{t.windowHelp}</p>
        <div className="flex flex-wrap gap-4">
          <Field label={t.start} error={errors.window_start?.message}>
            {(p) => (
              <input {...p} {...register('window_start')} type="time" className={inputClass} />
            )}
          </Field>
          <Field label={t.end} error={errors.window_end?.message}>
            {(p) => <input {...p} {...register('window_end')} type="time" className={inputClass} />}
          </Field>
        </div>
      </fieldset>
    </div>
  )
}

function RuleGroup({
  legend,
  keys,
  name,
  form,
}: {
  legend: string
  keys: readonly string[]
  name: 'never_connected_rules' | 'mid_call_rules'
  form: UseFormReturn<RetryValues>
}) {
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      <div className="grid gap-1 sm:grid-cols-2">
        {keys.map((k) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register(`${name}.${k}` as Path<RetryValues>)} />
            {t.reasons[k] ?? k}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
