import { screen, waitFor, within } from '@testing-library/react'
import { axe } from 'jest-axe'
import { http, HttpResponse } from 'msw'
import { strings } from '../src/lib/strings'
import { server } from './server'
import { ALL_ROLES, campaign, renderApp } from './utils'

const t = strings.campaignDetail
const rp = strings.retryPolicy
const ac = strings.agentConfig
const ID = '6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d'
const path = `/campaigns/${ID}`
const retryPath = `${path}?tab=retry`

const retryPolicy = {
  id: 'p1',
  campaign_id: ID,
  max_retries: 2,
  retry_spacing_seconds: [30, 600],
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
  window_start: '10:00:00',
  window_end: '18:00:00',
}
const agentConfig = {
  id: 'a1',
  campaign_id: ID,
  persona_tone: 'Warm',
  script_skeleton: ['Greet', 'Ask about interest'],
  required_entity_fields: ['interest_level'],
  escalation_contact_method: 'email',
  prompt_template_version: 'v3',
  model_config_uuid: null,
}

function mockCampaign(over: Record<string, unknown> = {}) {
  server.use(
    http.get(`*/v1/campaigns/${ID}`, () => HttpResponse.json(campaign({ id: ID, ...over }))),
    http.get(`*/v1/campaigns/${ID}/contacts`, () =>
      HttpResponse.json({ total: 0, page: 1, items: [] }),
    ),
    http.get(`*/v1/campaigns/${ID}/retry-policy`, () => HttpResponse.json(retryPolicy)),
    http.get(`*/v1/campaigns/${ID}/agent-config`, () => HttpResponse.json(agentConfig)),
  )
}
const button = (name: string) => screen.findByRole('button', { name })

describe('route', () => {
  test('a malformed id shows not found and makes no request', async () => {
    renderApp('/campaigns/not-a-uuid')
    expect(await screen.findByText(strings.notFound.title)).toBeInTheDocument()
  })

  test('a 404 from the server shows not found', async () => {
    server.use(http.get(`*/v1/campaigns/${ID}`, () => HttpResponse.json({}, { status: 404 })))
    renderApp(path)
    expect(await screen.findByText(strings.notFound.title)).toBeInTheDocument()
  })

  test('a server error offers a retry', async () => {
    server.use(http.get(`*/v1/campaigns/${ID}`, () => HttpResponse.json({}, { status: 500 })))
    renderApp(path)
    expect(await screen.findByText(t.loadFailed)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: strings.retry })).toBeInTheDocument()
  })

  test('shows name, status, contact count and has no axe violations', async () => {
    mockCampaign()
    const { container } = renderApp(retryPath)
    expect(await screen.findByRole('heading', { name: 'Q4 outreach' })).toBeInTheDocument()
    expect(screen.getByText(t.contactCount(12))).toBeInTheDocument()
    await screen.findByLabelText(rp.maxRetries)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('roles', () => {
  test('Sales can read the campaign and see Contacts, but gets no actions or config tabs', async () => {
    mockCampaign()
    renderApp(path, ALL_ROLES.sales)
    await screen.findByRole('heading', { name: 'Q4 outreach' })
    const main = within(screen.getByRole('main'))
    for (const name of [t.action.activate, t.action.complete, t.sync])
      expect(main.queryByRole('button', { name })).toBeNull()
    expect(screen.getAllByRole('tab').map((x) => x.textContent)).toEqual([t.tabContacts])
  })

  test('Manager can change status but not sync, and sees no stale banner', async () => {
    mockCampaign({ workflow_synced: false })
    renderApp(path, ALL_ROLES.manager)
    await button(t.action.activate)
    expect(screen.queryByRole('button', { name: t.sync })).toBeNull()
    expect(screen.queryByText(t.staleBanner)).toBeNull()
  })

  test('Admin sees the sync button and the stale banner', async () => {
    mockCampaign({ workflow_synced: false })
    renderApp(path)
    await button(t.sync)
    expect(screen.getByText(t.staleBanner)).toBeInTheDocument()
  })

  test('no stale banner when the workflow is in sync', async () => {
    mockCampaign({ workflow_synced: true })
    renderApp(path)
    await button(t.sync)
    expect(screen.queryByText(t.staleBanner)).toBeNull()
  })
})

describe('status actions', () => {
  test.each([
    ['draft', ['activate']],
    ['active', ['pause', 'complete']],
    ['paused', ['resume', 'complete']],
    ['completed', []],
  ] as const)('%s offers %j', async (status, actions) => {
    mockCampaign({ status })
    renderApp(path, ALL_ROLES.manager)
    await screen.findByRole('heading', { name: 'Q4 outreach' })
    for (const a of ['activate', 'resume', 'pause', 'complete'] as const) {
      const present = screen.queryByRole('button', { name: t.action[a] })
      expect(Boolean(present)).toBe((actions as readonly string[]).includes(a))
    }
  })

  test('confirming sends the PATCH and toasts; cancelling sends nothing', async () => {
    mockCampaign()
    const bodies: unknown[] = []
    server.use(
      http.patch(`*/v1/campaigns/${ID}`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(campaign({ id: ID, status: 'active' }))
      }),
    )
    const { user } = renderApp(path, ALL_ROLES.manager)
    await user.click(await button(t.action.activate))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: strings.cancel }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(bodies).toEqual([])

    await user.click(screen.getByRole('button', { name: t.action.activate }))
    const again = await screen.findByRole('alertdialog')
    await user.click(within(again).getByRole('button', { name: t.action.activate }))
    expect(await screen.findByText(t.statusDone('Active'))).toBeInTheDocument()
    expect(bodies).toEqual([{ status: 'active' }])
  })

  test('Complete warns that it cannot be undone', async () => {
    mockCampaign({ status: 'active' })
    const { user } = renderApp(path, ALL_ROLES.manager)
    await user.click(await button(t.action.complete))
    expect(await screen.findByText(t.confirm.complete.body)).toBeInTheDocument()
  })

  test('Admin is warned when activating with an out-of-date workflow', async () => {
    mockCampaign({ workflow_synced: false })
    const { user } = renderApp(path)
    await user.click(await button(t.action.activate))
    expect(await screen.findByText(t.unsyncedWarning)).toBeInTheDocument()
  })

  test('a server refusal is shown as an error and the dialog closes', async () => {
    mockCampaign()
    server.use(
      http.patch(`*/v1/campaigns/${ID}`, () =>
        HttpResponse.json(
          { status: ['Cannot change status from draft to paused.'] },
          { status: 400 },
        ),
      ),
    )
    const { user } = renderApp(path, ALL_ROLES.manager)
    await user.click(await button(t.action.activate))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: t.action.activate }))
    expect(
      await screen.findByText('Cannot change status from draft to paused.'),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  })
})

describe('sync workflow', () => {
  test('confirming posts and toasts the workflow uuid', async () => {
    mockCampaign({ workflow_synced: false })
    let calls = 0
    server.use(
      http.post(`*/v1/campaigns/${ID}/sync-workflow`, () => {
        calls++
        return HttpResponse.json({ workflow_uuid: 'wf-123' })
      }),
    )
    const { user } = renderApp(path)
    await user.click(await button(t.sync))
    const dialog = await screen.findByRole('alertdialog')
    expect(calls).toBe(0)
    await user.click(within(dialog).getByRole('button', { name: t.sync }))
    expect(await screen.findByText(t.syncDone('wf-123'))).toBeInTheDocument()
    expect(calls).toBe(1)
    expect(screen.getByText(/Last sync in this session/)).toBeInTheDocument()
  })

  test('a 502 explains that Dograh failed', async () => {
    mockCampaign()
    server.use(
      http.post(`*/v1/campaigns/${ID}/sync-workflow`, () =>
        HttpResponse.json({ detail: 'Dograh workflow sync failed' }, { status: 502 }),
      ),
    )
    const { user } = renderApp(path)
    await user.click(await button(t.sync))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: t.sync }))
    expect(await screen.findByText(t.syncFailed)).toBeInTheDocument()
  })
})

describe('retry policy tab', () => {
  test('shows the stored values; time is not converted', async () => {
    mockCampaign()
    renderApp(retryPath)
    expect(await screen.findByLabelText(rp.maxRetries)).toHaveValue(2)
    expect(screen.getByLabelText(rp.spacing(1))).toHaveValue(30)
    expect(screen.getByLabelText(rp.spacing(2))).toHaveValue(600)
    expect(screen.getByLabelText(rp.start)).toHaveValue('10:00')
    expect(screen.getByLabelText(rp.end)).toHaveValue('18:00')
    expect(
      screen.getByLabelText(rp.reasons.no_answer!, { selector: '[name^="never"]' }),
    ).toBeChecked()
  })

  test('Admin changes retries; spacing rows follow; Save sends the full policy', async () => {
    mockCampaign()
    let body: Record<string, unknown> | undefined
    server.use(
      http.put(`*/v1/campaigns/${ID}/retry-policy`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...retryPolicy,
          max_retries: 3,
          retry_spacing_seconds: [30, 600, 600],
        })
      }),
    )
    const { user } = renderApp(retryPath)
    const retries = await screen.findByLabelText(rp.maxRetries)
    await user.clear(retries)
    await user.type(retries, '3')
    expect(screen.getByLabelText(rp.spacing(3))).toHaveValue(600)
    await user.click(screen.getByRole('button', { name: strings.config.save }))
    expect(await screen.findByText(strings.config.saved)).toBeInTheDocument()
    expect(body).toMatchObject({
      max_retries: 3,
      retry_spacing_seconds: [30, 600, 600],
      window_start: '10:00',
      window_end: '18:00',
    })
    expect(screen.getByRole('button', { name: strings.config.save })).toBeDisabled()
  })

  test('start after end is rejected before any request', async () => {
    mockCampaign()
    let calls = 0
    server.use(
      http.put(
        `*/v1/campaigns/${ID}/retry-policy`,
        () => (calls++, HttpResponse.json(retryPolicy)),
      ),
    )
    const { user } = renderApp(retryPath)
    const start = await screen.findByLabelText(rp.start)
    await user.clear(start)
    await user.type(start, '19:00')
    await user.click(screen.getByRole('button', { name: strings.config.save }))
    expect(await screen.findByText(rp.windowOrder)).toBeInTheDocument()
    expect(calls).toBe(0)
  })

  test('server validation errors land on the field', async () => {
    mockCampaign()
    server.use(
      http.put(`*/v1/campaigns/${ID}/retry-policy`, () =>
        HttpResponse.json({ window_end: ['Server says no.'] }, { status: 400 }),
      ),
    )
    const { user } = renderApp(retryPath)
    const spacing = await screen.findByLabelText(rp.spacing(1))
    await user.clear(spacing)
    await user.type(spacing, '45')
    await user.click(screen.getByRole('button', { name: strings.config.save }))
    expect(await screen.findByText('Server says no.')).toBeInTheDocument()
  })

  test('Manager sees the values read-only with no Save', async () => {
    mockCampaign()
    renderApp(retryPath, ALL_ROLES.manager)
    expect(await screen.findByLabelText(rp.maxRetries)).toBeDisabled()
    expect(screen.getByText(strings.config.readOnly)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: strings.config.save })).toBeNull()
  })

  test('a failing load offers a retry', async () => {
    mockCampaign()
    server.use(
      http.get(`*/v1/campaigns/${ID}/retry-policy`, () => HttpResponse.json({}, { status: 500 })),
    )
    renderApp(retryPath)
    expect(await screen.findByText(strings.config.loadFailed)).toBeInTheDocument()
  })
})

describe('agent config tab', () => {
  test('deep link opens the tab and shows the stored config with the template version', async () => {
    mockCampaign()
    renderApp(`${path}?tab=agent`)
    expect(await screen.findByLabelText(ac.tone)).toHaveValue('Warm')
    expect(screen.getByLabelText(ac.script)).toHaveValue('Greet\nAsk about interest')
    expect(screen.getByText('v3')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: t.agent })).toHaveAttribute('aria-selected', 'true')
  })

  test('an unknown tab value falls back to the Contacts tab', async () => {
    mockCampaign()
    renderApp(`${path}?tab=<script>`)
    expect(await screen.findByLabelText(strings.contacts.status)).toBeInTheDocument()
  })

  test('Admin saves; blank script lines are dropped and an empty model uuid becomes null', async () => {
    mockCampaign()
    let body: Record<string, unknown> | undefined
    server.use(
      http.put(`*/v1/campaigns/${ID}/agent-config`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(agentConfig)
      }),
    )
    const { user } = renderApp(`${path}?tab=agent`)
    const script = await screen.findByLabelText(ac.script)
    await user.clear(script)
    await user.type(script, 'One{Enter}{Enter}Two')
    await user.click(screen.getByRole('button', { name: strings.config.save }))
    await screen.findByText(strings.config.saved)
    expect(body).toMatchObject({ script_skeleton: ['One', 'Two'], model_config_uuid: null })
    expect(body).not.toHaveProperty('prompt_template_version')
  })

  test('an invalid model uuid is rejected client-side', async () => {
    mockCampaign()
    const { user } = renderApp(`${path}?tab=agent`)
    await user.type(await screen.findByLabelText(ac.model), 'nope')
    await user.click(screen.getByRole('button', { name: strings.config.save }))
    expect(await screen.findByText(ac.modelInvalid)).toBeInTheDocument()
  })

  test('Manager sees it read-only', async () => {
    mockCampaign()
    renderApp(`${path}?tab=agent`, ALL_ROLES.manager)
    expect(await screen.findByLabelText(ac.tone)).toBeDisabled()
    expect(screen.queryByRole('button', { name: strings.config.save })).toBeNull()
  })
})

describe('unsaved changes', () => {
  async function dirtyRetry() {
    mockCampaign()
    const r = renderApp(retryPath)
    const retries = await screen.findByLabelText(rp.maxRetries)
    await r.user.clear(retries)
    await r.user.type(retries, '1')
    return r
  }

  test('switching tab asks first; Keep editing stays with the edits', async () => {
    const { user } = await dirtyRetry()
    await user.click(screen.getByRole('tab', { name: t.agent }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: t.unsavedStay }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(screen.getByLabelText(rp.maxRetries)).toHaveValue(1)
  })

  test('Discard changes leaves for the other tab', async () => {
    const { user } = await dirtyRetry()
    await user.click(screen.getByRole('tab', { name: t.agent }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: t.unsavedLeave }))
    expect(await screen.findByLabelText(ac.tone)).toBeInTheDocument()
  })

  test('Reset restores the stored values and clears the guard', async () => {
    const { user } = await dirtyRetry()
    await user.click(screen.getByRole('button', { name: strings.config.reset }))
    expect(screen.getByLabelText(rp.maxRetries)).toHaveValue(2)
    await user.click(screen.getByRole('tab', { name: t.agent }))
    expect(await screen.findByLabelText(ac.tone)).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  test('a clean form navigates without asking', async () => {
    mockCampaign()
    const { user } = renderApp(retryPath)
    await screen.findByLabelText(rp.maxRetries)
    await user.click(screen.getByRole('tab', { name: t.agent }))
    expect(await screen.findByLabelText(ac.tone)).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })
})
