import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { strings } from '../src/lib/strings'
import { MAX_UPLOAD_BYTES } from '../src/lib/upload'
import { server } from './server'
import { ALL_ROLES, campaign, renderApp } from './utils'

const t = strings.createCampaign
const csv = (name = 'contacts.csv') =>
  new File(['phone_number\n+14155550100\n'], name, { type: 'text/csv' })

async function fill(
  user: ReturnType<typeof userEvent.setup>,
  file: File | null = csv(),
  name = 'Q4 outreach',
) {
  const nameInput = await screen.findByLabelText(t.name)
  if (name) await user.type(nameInput, name)
  if (file) await user.upload(screen.getByLabelText(t.file), file)
}
const submit = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole('button', { name: t.submit }))

describe.each([
  ['Admin', ALL_ROLES.admin],
  ['Campaign Manager', ALL_ROLES.manager],
])('as %s', (_label, roles) => {
  test('creates a draft, sends multipart name + file, toasts and goes to the detail page', async () => {
    let form: FormData | undefined
    server.use(
      http.post('*/v1/campaigns', async ({ request }) => {
        form = await request.formData()
        return HttpResponse.json(campaign({ id: 'd4444444-4444-4444-8444-444444444444' }), {
          status: 201,
        })
      }),
    )
    const { user, router } = renderApp('/campaigns/new', roles)
    await fill(user)
    await submit(user)
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        '/campaigns/d4444444-4444-4444-8444-444444444444',
      ),
    )
    expect(form?.get('name')).toBe('Q4 outreach')
    // (jsdom's File loses its filename through Node's fetch, so check the content instead)
    expect(await (form?.get('contact_file') as File).text()).toBe('phone_number\n+14155550100\n')
    expect(form?.has('retry_policy')).toBe(false) // never sent from this screen
    expect(screen.getByText(t.created)).toBeInTheDocument()
  })
})

test('explains that a new campaign is a draft and offers a sample CSV with fake numbers', async () => {
  const { container } = renderApp('/campaigns/new')
  expect(await screen.findByText(t.draftNote)).toBeInTheDocument()
  const link = screen.getByRole('link', { name: t.sample })
  expect(link).toHaveAttribute('download', 'sample-contacts.csv')
  const body = decodeURIComponent(link.getAttribute('href')!.split(',')[1]!)
  expect(body).toBe('phone_number\n+10000000000\n+10000000001\n')
  expect(screen.getByText(t.sampleNote)).toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
})

test('shows the chosen file with its size and lets the user remove it', async () => {
  const { user } = renderApp('/campaigns/new')
  await fill(user, csv(), '')
  const group = screen.getByRole('group', { name: t.file })
  expect(group).toHaveTextContent('contacts.csv')
  expect(group).toHaveTextContent(/\d+ B/)
  await user.click(screen.getByRole('button', { name: t.remove }))
  expect(screen.queryByRole('group', { name: t.file })).not.toBeInTheDocument()
  expect(screen.getByLabelText(t.file)).toBeInTheDocument()
})

describe('client-side checks (the server stays the real validator)', () => {
  let requests = 0
  beforeEach(() => {
    requests = 0
    server.use(
      http.post('*/v1/campaigns', () => {
        requests++
        return HttpResponse.json(campaign(), { status: 201 })
      }),
    )
  })

  test('name and file are required', async () => {
    const { user } = renderApp('/campaigns/new')
    await screen.findByLabelText(t.name)
    await submit(user)
    expect(await screen.findByText(strings.login.required)).toBeInTheDocument()
    expect(screen.getByText(t.fileRequired)).toBeInTheDocument()
    expect(requests).toBe(0)
  })

  test('only .csv and .xlsx are accepted', async () => {
    renderApp('/campaigns/new')
    const user = userEvent.setup({ applyAccept: false })
    await fill(user, new File(['x'], 'contacts.txt'))
    await submit(user)
    expect(await screen.findByText(t.fileType)).toBeInTheDocument()
    expect(requests).toBe(0)
  })

  test('empty files are rejected', async () => {
    const { user } = renderApp('/campaigns/new')
    await fill(user, new File([], 'empty.csv'))
    expect(await screen.findByText(t.fileEmpty)).toBeInTheDocument()
    await submit(user)
    expect(requests).toBe(0)
  })

  test('files over 10 MB are rejected', async () => {
    const { user } = renderApp('/campaigns/new')
    await fill(user, new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], 'big.csv'))
    expect(await screen.findByText(t.fileSize)).toBeInTheDocument()
    await submit(user)
    expect(requests).toBe(0)
  })

  test('names over 200 characters are rejected', async () => {
    const { user } = renderApp('/campaigns/new')
    await fill(user, csv(), '')
    const input = await screen.findByLabelText(t.name)
    input.removeAttribute('maxlength') // the browser would stop typing; the schema must still hold
    await user.click(input)
    await user.paste('x'.repeat(201))
    await submit(user)
    expect(await screen.findByText(t.nameMax)).toBeInTheDocument()
    expect(requests).toBe(0)
  })
})

describe('server errors', () => {
  test('no_valid_contacts is shown at the file field and the form stays usable', async () => {
    server.use(
      http.post('*/v1/campaigns', () =>
        HttpResponse.json(
          { code: 'no_valid_contacts', message: 'No valid contacts found in the file.' },
          { status: 400 },
        ),
      ),
    )
    const { user, router } = renderApp('/campaigns/new')
    await fill(user)
    await submit(user)
    expect(await screen.findByText('No valid contacts found in the file.')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/campaigns/new')
    expect(screen.getByRole('button', { name: t.submit })).toBeEnabled()
  })

  test('field errors are mapped onto the inputs', async () => {
    server.use(
      http.post('*/v1/campaigns', () =>
        HttpResponse.json(
          { name: ['Name already used.'], contact_file: ['The file could not be read.'] },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderApp('/campaigns/new')
    await fill(user)
    await submit(user)
    expect(await screen.findByText('Name already used.')).toBeInTheDocument()
    expect(screen.getByText('The file could not be read.')).toBeInTheDocument()
  })

  test('a 403 is explained instead of crashing', async () => {
    server.use(
      http.post('*/v1/campaigns', () => HttpResponse.json({ detail: 'no' }, { status: 403 })),
    )
    const { user } = renderApp('/campaigns/new', ALL_ROLES.manager)
    await fill(user)
    await submit(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(t.noPermission)
  })
})

test('the submit button is disabled while the request is in flight, so it cannot double-submit', async () => {
  let requests = 0
  server.use(
    http.post('*/v1/campaigns', async () => {
      requests++
      await new Promise((r) => setTimeout(r, 150))
      return HttpResponse.json(campaign(), { status: 201 })
    }),
  )
  const { user } = renderApp('/campaigns/new')
  await fill(user)
  await submit(user)
  const busy = await screen.findByRole('button', { name: t.submitting })
  expect(busy).toBeDisabled()
  await user.click(busy)
  await waitFor(() => expect(requests).toBe(1))
})

describe('cancel', () => {
  test('leaves straight away when nothing was entered', async () => {
    const { user, router } = renderApp('/campaigns/new')
    await screen.findByLabelText(t.name)
    await user.click(screen.getByRole('button', { name: strings.cancel }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/campaigns'))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  test('asks first when the form is dirty; Keep editing stays, Discard leaves', async () => {
    server.use(http.get('*/v1/campaigns', () => HttpResponse.json([])))
    const { user, router } = renderApp('/campaigns/new')
    await fill(user, null, 'Half done')
    await user.click(screen.getByRole('button', { name: strings.cancel }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent(t.discardTitle)
    await user.click(screen.getByRole('button', { name: t.keepEditing }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(router.state.location.pathname).toBe('/campaigns/new')
    expect(screen.getByLabelText(t.name)).toHaveValue('Half done')

    await user.click(screen.getByRole('button', { name: strings.cancel }))
    await user.click(await screen.findByRole('button', { name: t.discard }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/campaigns'))
  })
})
