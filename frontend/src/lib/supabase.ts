import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

/** True when frontend/.env.local has a real project URL and publishable key. */
export const supabaseConfigured =
  typeof url === 'string' &&
  url.startsWith('https://') &&
  !url.includes('<project') &&
  typeof key === 'string' &&
  key.length > 20 &&
  !key.startsWith('sb_secret')

export const supabase = createClient(
  supabaseConfigured ? url : 'https://placeholder.supabase.co',
  supabaseConfigured ? key : 'sb_publishable_placeholder_not_configured',
)
