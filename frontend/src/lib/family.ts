import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { formatApiError } from './apiError'

/** The MVP assumes one family per account: the first one you joined. */
export function useFamily() {
  return useQuery({
    queryKey: ['families'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/families')
      if (error || !data) throw new Error(formatApiError(error, 'we could not load your family.'))
      return data
    },
    select: (families) => families[0] ?? null,
  })
}

export function useFamilyTree(familyId: string | undefined) {
  return useQuery({
    queryKey: ['tree', familyId],
    enabled: !!familyId,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/families/{family_id}/tree', {
        params: { path: { family_id: familyId! } },
      })
      if (error || !data) throw new Error(formatApiError(error, 'we could not load your family tree.'))
      return data
    },
  })
}

export function useFamilyInvites(familyId: string | undefined) {
  return useQuery({
    queryKey: ['invites', familyId],
    enabled: !!familyId,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/families/{family_id}/invites', {
        params: { path: { family_id: familyId! } },
      })
      if (error || !data) throw new Error(formatApiError(error, 'we could not load invitations.'))
      return data
    },
  })
}
