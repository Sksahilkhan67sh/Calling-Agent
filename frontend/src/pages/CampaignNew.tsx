import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { ApiError } from '../api/api'
import { useCreateCampaign } from '../api/queries'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Field, inputClass } from '../components/Field'
import { useToast } from '../components/Toast'
import { strings } from '../lib/strings'
import { SAMPLE_CSV_HREF, formatBytes, validateContactFile } from '../lib/upload'

const t = strings.createCampaign
const schema = z.object({
  name: z.string().trim().min(1, strings.login.required).max(200, t.nameMax),
  file: z
    .custom<File>((v) => v instanceof File, t.fileRequired)
    .superRefine((f, ctx) => {
      const message = validateContactFile(f)
      if (message) ctx.addIssue({ code: 'custom', message })
    }),
})
type Values = z.input<typeof schema>

export function CampaignNew() {
  const navigate = useNavigate()
  const toast = useToast()
  const create = useCreateCampaign()
  const [dragging, setDragging] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setValue,
    setError,
    control,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: '' } })

  const file = useWatch({ control, name: 'file' })
  const name = useWatch({ control, name: 'name' })
  const dirty = Boolean(name) || Boolean(file)
  const busy = create.isPending

  const pick = (f: File | undefined) =>
    setValue('file', f as File, { shouldValidate: true, shouldDirty: true })

  const onSubmit = handleSubmit(async ({ name, file }) => {
    setFormError(null)
    try {
      const campaign = await create.mutateAsync({ name, file })
      toast.success(t.created)
      navigate(`/campaigns/${campaign.id}`)
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      if (e.code === 'no_valid_contacts') return setError('file', { message: e.message })
      if (e.status === 403) return setFormError(t.noPermission)
      const mapped = {
        name: e.fieldErrors.name?.[0],
        file: e.fieldErrors.contact_file?.[0],
      }
      if (mapped.name) setError('name', { message: mapped.name })
      if (mapped.file) setError('file', { message: mapped.file })
      if (!mapped.name && !mapped.file) setFormError(e.message)
    }
  })

  const cancel = () => (dirty ? setConfirmDiscard(true) : navigate('/campaigns'))

  return (
    <section className="max-w-xl">
      <h1 className="mb-2 text-2xl font-semibold">{t.title}</h1>
      <p className="mb-6 text-sm text-muted">{t.draftNote}</p>

      <form onSubmit={onSubmit} noValidate className="space-y-5">
        <Field label={t.name} error={errors.name?.message}>
          {(p) => (
            <input
              {...p}
              {...register('name')}
              type="text"
              maxLength={200}
              autoComplete="off"
              className={inputClass}
            />
          )}
        </Field>

        <Field label={t.file} error={errors.file?.message} help={t.fileHelp}>
          {(p) => (
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                pick(e.dataTransfer.files[0])
              }}
              className={`rounded-md border-2 border-dashed p-4 ${dragging ? 'border-primary bg-card' : 'border-border'}`}
            >
              {file instanceof File ? (
                <div
                  role="group"
                  aria-label={t.file}
                  className="flex items-center justify-between gap-3"
                >
                  <span className="min-w-0 truncate text-sm">
                    {file.name} <span className="text-muted">({formatBytes(file.size)})</span>
                  </span>
                  <Button variant="secondary" onClick={() => pick(undefined)}>
                    {t.remove}
                  </Button>
                </div>
              ) : (
                <div className="text-sm">
                  <p className="mb-2 text-muted">{t.dropHere}</p>
                  <input
                    {...p}
                    type="file"
                    accept=".csv,.xlsx"
                    onChange={(e) => pick(e.target.files?.[0])}
                  />
                </div>
              )}
            </div>
          )}
        </Field>

        <p className="text-sm">
          <a
            href={SAMPLE_CSV_HREF}
            download="sample-contacts.csv"
            className="text-primary underline"
          >
            {t.sample}
          </a>
          <span className="mt-1 block text-xs text-muted">{t.sampleNote}</span>
        </p>

        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}

        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>
            {busy ? t.submitting : t.submit}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={cancel}>
            {strings.cancel}
          </Button>
        </div>
      </form>

      <ConfirmDialog
        open={confirmDiscard}
        title={t.discardTitle}
        description={t.discardBody}
        confirmLabel={t.discard}
        cancelLabel={t.keepEditing}
        danger
        onConfirm={() => navigate('/campaigns')}
        onCancel={() => setConfirmDiscard(false)}
      />
    </section>
  )
}
