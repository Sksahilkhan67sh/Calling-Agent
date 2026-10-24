import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { Outlet } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { ToastProvider } from './components/Toast'

// Providers live inside the router because AuthProvider navigates.
export function Root({ queryClient }: { queryClient: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <Outlet />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  )
}
