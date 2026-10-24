import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import './index.css'
import { applyTheme, getTheme } from './lib/theme'
import { router } from './router'

applyTheme(getTheme()) // before first render, so there is no flash of the wrong theme

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
