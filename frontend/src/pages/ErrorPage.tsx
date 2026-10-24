import { Notice } from '../components/Notice'
import { strings } from '../lib/strings'

// Deliberately generic: error messages can contain server data, which must never reach the screen or console.
export function ErrorPage() {
  return (
    <main>
      <Notice title={strings.error.title}>
        <p>{strings.error.body}</p>
        <button
          type="button"
          className="mt-4 rounded-md bg-primary px-4 py-2 text-primary-fg"
          onClick={() => window.location.reload()}
        >
          {strings.error.reload}
        </button>
      </Notice>
    </main>
  )
}
