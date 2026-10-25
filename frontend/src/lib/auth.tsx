import type { Session } from '@supabase/supabase-js'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { supabase, supabaseConfigured } from '@/lib/supabase'

type AuthValue = {
  ready: boolean
  session: Session | null
  signOut: () => Promise<void>
}

const AuthCtx = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(
    supabaseConfigured ? undefined : null,
  )

  useEffect(() => {
    if (!supabaseConfigured) return
    let ignore = false
    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (!ignore) setSession(data.session)
      })
      .catch(() => {
        if (!ignore) setSession(null)
      })
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      if (!ignore) setSession(next)
    })
    return () => {
      ignore = true
      data.subscription.unsubscribe()
    }
  }, [])

  const signOut = useCallback(async () => {
    if (supabaseConfigured) {
      const { error } = await supabase.auth.signOut()
      if (error) throw error
    }
    setSession(null)
  }, [])

  return (
    <AuthCtx.Provider value={{ ready: session !== undefined, session: session ?? null, signOut }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() {
  const value = useContext(AuthCtx)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
