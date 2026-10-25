import { useQueryClient } from '@tanstack/react-query'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router'
import { ScreenBody, YellowButton, BootScreen } from '@/components/ui/chrome'
import { useAuth } from '@/lib/auth'
import { useProfile } from '@/lib/profile'
import { readReturnTo, rememberReturnTo } from '@/lib/returnTo'
import { supabaseConfigured } from '@/lib/supabase'
import { Home } from '@/routes/Home'
import { Welcome } from '@/routes/Welcome'

function waitingOnProfile(hasSession: boolean, hasData: boolean, isError: boolean) {
  return hasSession && supabaseConfigured && !hasData && !isError
}

export function ProfileError({ detail }: { detail?: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  async function logout() {
    try {
      await signOut()
    } catch {
      /* still leave the broken session */
    }
    qc.clear()
    navigate('/', { replace: true })
  }

  return (
    <ScreenBody screen="account-error">
      <h1 className="font-hand text-5xl leading-none font-bold">tell me more</h1>
      <p className="mt-4 font-sans text-lg leading-snug">
        {detail ?? 'we could not load your account from the server.'}
      </p>
      <div className="mt-auto flex flex-col gap-4">
        <YellowButton onClick={() => qc.invalidateQueries({ queryKey: ['profile'] })}>try again →</YellowButton>
        <button type="button" onClick={logout} className="font-hand text-[1.7rem] font-semibold">
          sign out
        </button>
      </div>
    </ScreenBody>
  )
}

/** `/` is the welcome screen until a session exists, then home after onboarding. */
export function Entry() {
  const { ready, session } = useAuth()
  const profile = useProfile()

  if (!ready) return <BootScreen />
  if (!session) return <Welcome />
  if (!supabaseConfigured) return <ProfileError detail="add the supabase keys in frontend/.env.local." />
  if (waitingOnProfile(true, !!profile.data, profile.isError)) return <BootScreen />
  if (profile.isError) return <ProfileError detail={profile.error.message} />
  if (profile.data?.age == null) return <Navigate to="/onboarding" replace />
  const returnTo = readReturnTo()
  if (returnTo) return <Navigate to={returnTo} replace />
  return <Home />
}

export function PublicOnly() {
  const location = useLocation()
  const { ready, session } = useAuth()
  const profile = useProfile()
  const editing = Boolean((location.state as { editing?: boolean } | null)?.editing)

  if (!ready) return <BootScreen />
  if (!session) return <Outlet />
  if (editing && location.pathname === '/sign-up') return <Outlet />
  if (!supabaseConfigured) return <ProfileError detail="add the supabase keys in frontend/.env.local." />
  if (waitingOnProfile(true, !!profile.data, profile.isError)) return <BootScreen />
  if (profile.isError) return <ProfileError detail={profile.error.message} />
  if (profile.data?.age == null) return <Navigate to="/onboarding" replace />
  return <Navigate to="/" replace />
}

export function RequireAuth() {
  const location = useLocation()
  const { ready, session } = useAuth()
  if (!ready) return <BootScreen />
  if (!session) {
    rememberReturnTo(location.pathname)
    return <Navigate to="/welcome" replace />
  }
  return <Outlet />
}

export function RequireOnboarding() {
  const location = useLocation()
  const profile = useProfile()
  if (!supabaseConfigured) return <ProfileError detail="add the supabase keys in frontend/.env.local." />
  if (waitingOnProfile(true, !!profile.data, profile.isError)) return <BootScreen />
  if (profile.isError) return <ProfileError detail={profile.error.message} />
  if (profile.data?.age == null) {
    rememberReturnTo(location.pathname)
    return <Navigate to="/onboarding" replace />
  }
  return <Outlet />
}
