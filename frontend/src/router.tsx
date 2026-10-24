import type { QueryClient } from '@tanstack/react-query'
import { Navigate, type RouteObject } from 'react-router-dom'
import { ADMIN, MANAGER, SALES } from './api/types'
import { RequireAuth, RequireRole } from './auth/guards'
import { Layout } from './components/Layout'
import { strings } from './lib/strings'
import { ErrorPage } from './pages/ErrorPage'
import { Forbidden } from './pages/Forbidden'
import { NotFound } from './pages/NotFound'
import { Root } from './Root'

const Loading = () => (
  <p role="status" aria-busy="true" className="p-8 text-muted">
    {strings.loading}…
  </p>
)

export const createRoutes = (queryClient: QueryClient): RouteObject[] => [
  {
    element: <Root queryClient={queryClient} />,
    errorElement: <ErrorPage />,
    HydrateFallback: Loading,
    children: [
      {
        path: 'login',
        lazy: async () => ({ Component: (await import('./pages/Login')).Login }),
      },
      {
        element: (
          <RequireAuth>
            <Layout />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <Navigate to="/campaigns" replace /> },
          {
            path: 'campaigns',
            handle: { crumb: strings.breadcrumb.campaigns },
            children: [
              {
                index: true,
                lazy: async () => {
                  const { Campaigns } = await import('./pages/Campaigns')
                  return {
                    element: (
                      <RequireRole roles={[ADMIN, MANAGER, SALES]}>
                        <Campaigns />
                      </RequireRole>
                    ),
                  }
                },
              },
              {
                path: 'new',
                handle: { crumb: strings.breadcrumb.newCampaign },
                lazy: async () => {
                  const { CampaignNew } = await import('./pages/CampaignNew')
                  return {
                    element: (
                      <RequireRole roles={[ADMIN, MANAGER]}>
                        <CampaignNew />
                      </RequireRole>
                    ),
                  }
                },
              },
            ],
          },
          { path: 'forbidden', element: <Forbidden /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
]
