import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { createQueryClient } from '../src/api/queries'
import { createRoutes } from '../src/router'
import { mockMe, mockNoRefresh } from './server'

export const ALL_ROLES = {
  admin: ['Admin'],
  manager: ['Campaign Manager'],
  sales: ['Sales/Follow-up'],
}

// For tests that install their own stateful /me handler.
export function renderRaw(path: string) {
  const queryClient = createQueryClient()
  const router = createMemoryRouter(createRoutes(queryClient), { initialEntries: [path] })
  const user = userEvent.setup()
  return { ...render(<RouterProvider router={router} />), router, queryClient, user }
}

export function renderApp(path: string, roles: string[] | null = ALL_ROLES.admin) {
  mockMe(roles)
  if (!roles) mockNoRefresh()
  return renderRaw(path)
}

export const campaign = (over: Partial<Record<string, unknown>> = {}) => ({
  id: '6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d',
  name: 'Q4 outreach',
  status: 'draft',
  contact_count: 12,
  created_at: '2026-10-20T08:30:00Z',
  ...over,
})
