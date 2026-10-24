import * as AlertDialog from '@radix-ui/react-alert-dialog'
import type { ReactNode } from 'react'
import { Button } from './Button'

interface Props {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel: string
  cancelLabel?: string | undefined
  onConfirm: () => void
  // Omit for a single-action dialog (e.g. session expired).
  onCancel?: (() => void) | undefined
  pending?: boolean
  danger?: boolean
  // Dialogs the person must answer (idle warning, session expired) ignore Escape.
  dismissable?: boolean
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  pending,
  danger,
  dismissable = true,
}: Props) {
  return (
    <AlertDialog.Root open={open} onOpenChange={(o) => !o && dismissable && onCancel?.()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 bg-black/50" />
        <AlertDialog.Content
          onEscapeKeyDown={(e) => !dismissable && e.preventDefault()}
          className="fixed top-1/2 left-1/2 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg p-5 shadow-xl"
        >
          <AlertDialog.Title className="text-lg font-semibold">{title}</AlertDialog.Title>
          <AlertDialog.Description asChild>
            <div className="mt-2 text-sm text-muted">{description}</div>
          </AlertDialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            {onCancel && (
              <AlertDialog.Cancel asChild>
                <Button
                  variant="secondary"
                  disabled={pending}
                  onClick={(e) => {
                    e.preventDefault() // the caller closes the dialog by changing `open`
                    onCancel()
                  }}
                >
                  {cancelLabel}
                </Button>
              </AlertDialog.Cancel>
            )}
            <AlertDialog.Action asChild>
              <Button
                variant={danger ? 'danger' : 'primary'}
                disabled={pending}
                onClick={(e) => {
                  e.preventDefault() // keep the dialog open until the caller closes it
                  onConfirm()
                }}
              >
                {confirmLabel}
              </Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
