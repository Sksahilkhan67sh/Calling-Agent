import { createBrowserRouter } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ErrorPage } from './pages/ErrorPage'
import { Forbidden } from './pages/Forbidden'
import { NotFound } from './pages/NotFound'

export const routes = [
  {
    element: <Layout />,
    errorElement: <ErrorPage />,
    children: [
      { path: 'forbidden', element: <Forbidden /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
