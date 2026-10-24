import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'
import { createQueryClient } from './api/queries'
import { applyTheme, getTheme } from './lib/theme'
import { createRoutes } from './router'

applyTheme(getTheme()) // before first render, so there is no flash of the wrong theme

const router = createBrowserRouter(createRoutes(createQueryClient()))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
