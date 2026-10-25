import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatApiError } from '@/lib/apiError'
import { useAuth } from '@/lib/auth'
import { supabase, supabaseConfigured } from '@/lib/supabase'

export function profileKey(userId: string) {
  return ['profile', userId] as const
}

export function useProfile() {
  const { ready, session } = useAuth()
  return useQuery({
    queryKey: session ? profileKey(session.user.id) : ['profile', 'signed-out'],
    enabled: ready && !!session && supabaseConfigured,
    staleTime: 30_000,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/profile')
      if (response.status === 401) {
        await supabase.auth.signOut()
        throw new Error('session expired. sign in again.')
      }
      if (response.status === 502 || response.status === 503 || response.status === 504) {
        throw new Error('the server is unavailable. start the backend and try again.')
      }
      if (error || !data) throw new Error(formatApiError(error, 'we could not load your account.'))
      return data
    },
  })
}
