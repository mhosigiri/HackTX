import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'
import {
  BackLink,
  FormError,
  HandLink,
  InviteNote,
  PersonMark,
  ScreenBody,
  YellowButton,
} from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'
import { PasswordField, TextField } from '@/components/ui/fields'
import { friendlyAuthError, missingSupabaseConfig } from '@/lib/apiError'
import { useAuth } from '@/lib/auth'
import { readDisplayName, stashDisplayName } from '@/lib/pendingProfile'
import { supabase, supabaseConfigured } from '@/lib/supabase'

export function SignUp() {
  useScreenTitle('create account')
  const navigate = useNavigate()
  const location = useLocation()
  const { session } = useAuth()
  const editing = Boolean((location.state as { editing?: boolean } | null)?.editing && session)
  const [name, setName] = useState(() => readDisplayName())
  const [email, setEmail] = useState(session?.user.email ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [checkEmail, setCheckEmail] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const displayName = name.trim()
    if (!displayName) {
      setError('add your name.')
      return
    }
    if (!session && !email.includes('@')) {
      setError('add a valid email.')
      return
    }
    if (!session && password.length < 6) {
      setError('use at least 6 characters.')
      return
    }
    stashDisplayName(displayName)
    if (session) {
      navigate('/onboarding')
      return
    }
    if (!supabaseConfigured) {
      setError(missingSupabaseConfig)
      return
    }
    setBusy(true)
    const { data, error: authError } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        emailRedirectTo: window.location.origin,
        data: { display_name: displayName },
      },
    })
    setBusy(false)
    if (authError) {
      setError(friendlyAuthError(authError.message))
      return
    }
    if (data.user && Array.isArray(data.user.identities) && data.user.identities.length === 0) {
      setError('an account with that email already exists. sign in instead.')
      return
    }
    if (!data.session) {
      setCheckEmail(true)
      return
    }
    navigate('/onboarding', { replace: true })
  }

  if (checkEmail) {
    return (
      <ScreenBody screen="check-email">
        <BackLink to="/welcome" />
        <h1 className="mt-6 font-hand text-5xl leading-none font-bold">check your email</h1>
        <p className="mt-4 font-sans text-lg leading-snug">
          we sent a link to {email.trim()}. open it, then sign in to finish making it yours.
        </p>
        <InviteNote className="mt-4" />
        <div className="mt-auto">
          <YellowButton to="/sign-in">sign in →</YellowButton>
        </div>
      </ScreenBody>
    )
  }

  return (
    <ScreenBody screen="sign-up" className="pt-6 pb-5">
      <BackLink to={editing ? '/onboarding' : '/welcome'} />
      <h1 className="mt-4 font-hand text-5xl leading-none font-bold">create account</h1>
      <InviteNote className="mt-4" />
      <div className="mt-4 flex justify-center">
        <PersonMark />
      </div>
      <form onSubmit={submit} className="mt-4 flex flex-1 flex-col gap-3" noValidate>
        <TextField
          label="your name"
          name="name"
          autoComplete="name"
          value={name}
          onChange={setName}
        />
        <TextField
          label="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
          readOnly={editing}
        />
        {!editing && (
          <PasswordField
            label="password"
            name="password"
            autoComplete="new-password"
            value={password}
            onChange={setPassword}
          />
        )}
        <div className="mt-auto flex flex-col gap-3 pt-4">
          <FormError>{error}</FormError>
          <YellowButton type="submit" disabled={busy}>
            {busy ? 'please wait…' : 'continue →'}
          </YellowButton>
          {!editing && <HandLink to="/sign-in">sign in</HandLink>}
        </div>
      </form>
    </ScreenBody>
  )
}
