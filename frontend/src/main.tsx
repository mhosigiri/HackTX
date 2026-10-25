import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'
import { FrameLayout } from '@/components/ui/chrome'
import { AuthProvider } from '@/lib/auth'
import { DisplayModeProvider } from '@/lib/displayMode'
import { Archive } from '@/routes/Archive'
import { Account } from '@/routes/Account'
import { Entry, PublicOnly, RequireAuth, RequireOnboarding } from '@/routes/AuthGate'
import { Capture } from '@/routes/Capture'
import { ChooseStoryteller } from '@/routes/ChooseStoryteller'
import { Family } from '@/routes/Family'
import { Heirloom } from '@/routes/Heirloom'
import { Interview } from '@/routes/Interview'
import { InviteRelative } from '@/routes/InviteRelative'
import { InviteResponse } from '@/routes/InviteResponse'
import { MyRequests } from '@/routes/MyRequests'
import { Notifications } from '@/routes/Notifications'
import { Onboarding } from '@/routes/Onboarding'
import { PublicStory } from '@/routes/PublicStory'
import { RecordStory } from '@/routes/RecordStory'
import { RequestConfirm } from '@/routes/RequestConfirm'
import { RequestDetail } from '@/routes/RequestDetail'
import { Review } from '@/routes/Review'
import { ReviewShare } from '@/routes/ReviewShare'
import { Settings } from '@/routes/Settings'
import { Shelf } from '@/routes/Shelf'
import { SignIn } from '@/routes/SignIn'
import { SignUp } from '@/routes/SignUp'
import { Soon } from '@/routes/Soon'
import { Tell } from '@/routes/Tell'
import { Welcome } from '@/routes/Welcome'
import './index.css'

const queryClient = new QueryClient()

const router = createBrowserRouter([
  {
    element: <FrameLayout />,
    children: [
      { path: '/', element: <Entry /> },
      {
        element: <PublicOnly />,
        children: [
          { path: '/welcome', element: <Welcome /> },
          { path: '/sign-in', element: <SignIn /> },
          { path: '/sign-up', element: <SignUp /> },
        ],
      },
      { path: '/s/:heirloomId', element: <PublicStory /> },
      {
        element: <RequireAuth />,
        children: [
          { path: '/onboarding', element: <Onboarding /> },
          {
            element: <RequireOnboarding />,
            children: [
              { path: '/account', element: <Account /> },
              { path: '/dates', element: <Soon title="important dates" /> },
              { path: '/availability', element: <Soon title="family availability" /> },
              { path: '/timeline', element: <Soon title="timeline" /> },
              { path: '/stories', element: <Shelf /> },
              { path: '/capture', element: <Capture /> },
              { path: '/review', element: <Review /> },
              { path: '/archive', element: <Archive /> },
              { path: '/choose/:heirloomId', element: <ChooseStoryteller /> },
              { path: '/request-confirm/:requestId', element: <RequestConfirm /> },
              { path: '/requests', element: <MyRequests /> },
              { path: '/requests/:requestId', element: <RequestDetail /> },
              { path: '/answer/:requestId', element: <RecordStory /> },
              { path: '/tell', element: <Tell /> },
              { path: '/share/:heirloomId', element: <ReviewShare /> },
              { path: '/notifications', element: <Notifications /> },
              { path: '/settings', element: <Settings /> },
              { path: '/h/:heirloomId', element: <Heirloom /> },
              { path: '/interview/:interviewId', element: <Interview /> },
              { path: '/family', element: <Family /> },
              { path: '/family/invite/:personId', element: <InviteRelative /> },
              { path: '/invite/:inviteId', element: <InviteResponse /> },
            ],
          },
        ],
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DisplayModeProvider>
          <RouterProvider router={router} />
        </DisplayModeProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
