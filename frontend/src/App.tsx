import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AppLayout } from '@/layouts/AppLayout'
import DashboardPage from '@/pages/DashboardPage'
import CommentLettersPage from '@/pages/CommentLettersPage'
import LetterDetailPage from '@/pages/LetterDetailPage'
import TasksPage from '@/pages/TasksPage'
import PermitsPage from '@/pages/PermitsPage'
import PermitDetailPage from '@/pages/PermitDetailPage'
import PayoutsPage from '@/pages/PayoutsPage'
import IntegrationsPage from '@/pages/IntegrationsPage'
import SettingsPage from '@/pages/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
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
    </QueryClientProvider>
  )
}
