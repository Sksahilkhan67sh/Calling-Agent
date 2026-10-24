import type { UseFormReturn } from 'react-hook-form'
import { z } from 'zod'
import { ENTITY_FIELDS, type AgentConfig } from '../../api/types'
import { strings } from '../../lib/strings'
import { isUuid } from '../../lib/uuid'
import { Field, inputClass } from '../Field'

const t = strings.agentConfig

export const agentSchema = z.object({
  persona_tone: z.string().trim().max(255),
  // One step per line; blank lines are dropped on save
  script: z.string(),
  required_entity_fields: z.array(z.enum(ENTITY_FIELDS)),
  escalation_contact_method: z.string().trim().max(255),
  model_config_uuid: z
    .string()
    .trim()
    .refine((v) => v === '' || isUuid(v), t.modelInvalid),
})
export type AgentValues = z.input<typeof agentSchema>

export const agentDefaults: AgentValues = {
  persona_tone: '',
  script: '',
  required_entity_fields: [],
  escalation_contact_method: '',
  model_config_uuid: '',
}

export const agentFromServer = (a: AgentConfig): AgentValues => ({
  persona_tone: a.persona_tone,
  script: a.script_skeleton.join('\n'),
  required_entity_fields: a.required_entity_fields,
  escalation_contact_method: a.escalation_contact_method,
  model_config_uuid: a.model_config_uuid ?? '',
})

export const agentToPayload = (v: AgentValues) => ({
  persona_tone: v.persona_tone,
  script_skeleton: v.script
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean),
  required_entity_fields: v.required_entity_fields,
  escalation_contact_method: v.escalation_contact_method,
  model_config_uuid: v.model_config_uuid || null,
})

export const agentServerFields: Record<string, keyof AgentValues> = {
  persona_tone: 'persona_tone',
  script_skeleton: 'script',
  required_entity_fields: 'required_entity_fields',
  escalation_contact_method: 'escalation_contact_method',
  model_config_uuid: 'model_config_uuid',
}

export function AgentConfigFields({
  form,
  version,
}: {
  form: UseFormReturn<AgentValues>
  version?: string | undefined
}) {
  const {
    register,
    formState: { errors },
  } = form
  return (
    <div className="space-y-5">
      <Field label={t.tone} error={errors.persona_tone?.message}>
        {(p) => (
          <input
            {...p}
            {...register('persona_tone')}
            type="text"
            maxLength={255}
            className={inputClass}
          />
        )}
      </Field>
      <Field label={t.script} help={t.scriptHelp} error={errors.script?.message}>
        {(p) => <textarea {...p} {...register('script')} rows={6} className={inputClass} />}
      </Field>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">{t.entities}</legend>
        <div className="grid gap-1 sm:grid-cols-2">
          {ENTITY_FIELDS.map((f) => (
            <label key={f} className="flex items-center gap-2 text-sm">
              <input type="checkbox" value={f} {...register('required_entity_fields')} />
              {t.fields[f] ?? f}
            </label>
          ))}
        </div>
        {errors.required_entity_fields?.message && (
          <p role="alert" className="mt-1 text-sm text-danger">
            {errors.required_entity_fields.message}
          </p>
        )}
      </fieldset>
      <Field label={t.escalation} error={errors.escalation_contact_method?.message}>
        {(p) => (
          <input
            {...p}
            {...register('escalation_contact_method')}
            type="text"
            maxLength={255}
            className={inputClass}
          />
        )}
      </Field>
      <Field label={t.model} help={t.modelHelp} error={errors.model_config_uuid?.message}>
        {(p) => (
          <input
            {...p}
            {...register('model_config_uuid')}
            type="text"
            autoComplete="off"
            spellCheck={false}
            className={inputClass}
          />
        )}
      </Field>
      {version && (
        <p className="text-sm text-muted">
          {t.version}: <span className="text-fg">{version}</span>
        </p>
      )}
    </div>
  )
}
