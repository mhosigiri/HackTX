import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import {
  BackLink,
  FormError,
  HandLink,
  InviteNote,
  ScreenBody,
  YellowButton,
} from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'
import { PasswordField, TextField } from '@/components/ui/fields'
import { friendlyAuthError, missingSupabaseConfig } from '@/lib/apiError'
import { useAuth } from '@/lib/auth'
import { supabase, supabaseConfigured } from '@/lib/supabase'

export function SignIn() {
  useScreenTitle('sign in')
  const navigate = useNavigate()
  const { session } = useAuth()
  const [email, setEmail] = useState(session?.user.email ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!email.includes('@')) {
      setError('add a valid email.')
      return
    }
    if (!password) {
      setError('add your password.')
      return
    }
    if (!supabaseConfigured) {
      setError(missingSupabaseConfig)
      return
    }
    setBusy(true)
    const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    setBusy(false)
    if (authError) {
      setError(friendlyAuthError(authError.message))
      return
    }
    navigate('/', { replace: true })
  }

  return (
    <ScreenBody screen="sign-in" className="pt-6 pb-5">
      <BackLink to="/welcome" />
      <h1 className="mt-4 font-hand text-5xl leading-none font-bold">sign in</h1>
      <InviteNote className="mt-4" />
      <form onSubmit={submit} className="mt-6 flex flex-1 flex-col gap-4" noValidate>
        <TextField
          label="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
        />
        <PasswordField
          label="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <div className="mt-auto flex flex-col gap-3 pt-5">
          <FormError>{error}</FormError>
          <YellowButton type="submit" disabled={busy}>
            {busy ? 'signing in…' : 'sign in →'}
          </YellowButton>
          <HandLink to="/sign-up">create account</HandLink>
        </div>
      </form>
    </ScreenBody>
  )
}
