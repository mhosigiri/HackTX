export function formatApiError(error: unknown, fallback = 'something went wrong. try again.'): string {
  if (!error || typeof error !== 'object') return fallback
  const detail = 'detail' in error ? (error as { detail: unknown }).detail : undefined
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const first = detail[0]
    if (first && typeof first === 'object' && 'msg' in first) {
      const msg = (first as { msg?: unknown }).msg
      if (typeof msg === 'string' && msg.trim()) return msg
    }
  }
  return fallback
}

export function friendlyAuthError(message: string): string {
  const lower = message.toLowerCase()
  if (lower.includes('invalid login') || lower.includes('invalid credentials')) {
    return 'that email and password do not match.'
  }
  if (lower.includes('already registered') || lower.includes('already been registered')) {
    return 'an account with that email already exists. sign in instead.'
  }
  if (lower.includes('rate limit')) {
    return 'too many emails were just sent. wait a few minutes and try again.'
  }
  if (lower.includes('password')) return message
  if (lower.includes('fetch') || lower.includes('network') || lower.includes('failed to fetch')) {
    return 'we could not reach sign-in. check your connection.'
  }
  if (lower.includes('email')) return 'check that email and try again.'
  return 'something went wrong. try again.'
}

export const missingSupabaseConfig =
  'add VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env.local.'
