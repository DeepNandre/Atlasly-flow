import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AppLayout } from '@/layouts/AppLayout'
import { AuthProvider } from '@/hooks/useAuth'

const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const CommentLettersPage = lazy(() => import('@/pages/CommentLettersPage'))
const LetterDetailPage = lazy(() => import('@/pages/LetterDetailPage'))
const TasksPage = lazy(() => import('@/pages/TasksPage'))
const PermitsPage = lazy(() => import('@/pages/PermitsPage'))
const PermitDetailPage = lazy(() => import('@/pages/PermitDetailPage'))
const PayoutsPage = lazy(() => import('@/pages/PayoutsPage'))
const IntegrationsPage = lazy(() => import('@/pages/IntegrationsPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

function RouteLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 rounded-full border-2 border-atlasly-teal border-t-transparent animate-spin" />
        <p className="text-sm text-atlasly-muted">Loading workspace…</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<RouteLoader />}>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="letters" element={<CommentLettersPage />} />
                <Route path="letters/:id" element={<LetterDetailPage />} />
                <Route path="tasks" element={<TasksPage />} />
                <Route path="permits" element={<PermitsPage />} />
                <Route path="permits/:id" element={<PermitDetailPage />} />
                <Route path="payouts" element={<PayoutsPage />} />
                <Route path="integrations" element={<IntegrationsPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: '#fffdf8',
              border: '1px solid #dad3c2',
              color: '#121412',
            },
          }}
        />
      </AuthProvider>
    </QueryClientProvider>
  )
}
