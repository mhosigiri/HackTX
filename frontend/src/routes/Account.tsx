import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { BackLink, FormError, ScreenBody } from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'
import { useAuth } from '@/lib/auth'
import { clearDisplayName } from '@/lib/pendingProfile'
import { useProfile } from '@/lib/profile'
import { activeTheme, applyTheme, type ThemeChoice } from '@/lib/theme'

export function Account() {
  useScreenTitle('your account')
  const navigate = useNavigate()
  const { session, signOut } = useAuth()
  const profile = useProfile()
  const qc = useQueryClient()
  const [theme, setTheme] = useState<ThemeChoice>(() => activeTheme())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const name = profile.data?.display_name?.trim() || ''
  const email = session?.user.email ?? ''

  function choose(next: ThemeChoice) {
    applyTheme(next)
    setTheme(next)
  }

  async function logout() {
    setBusy(true)
    setError(null)
    try {
      await signOut()
      clearDisplayName()
      qc.clear()
      navigate('/', { replace: true })
    } catch {
      setBusy(false)
      setError('we could not sign out. try again.')
    }
  }

  const choiceClass = (id: ThemeChoice) =>
    `h-12 rounded-full border-2 border-ink font-hand text-[1.7rem] leading-none font-semibold ${
      theme === id ? 'bg-sun text-black' : 'bg-paper text-ink'
    }`

  return (
    <ScreenBody screen="account">
      <BackLink to="/" />
      <h1 className="mt-6 font-hand text-5xl leading-none font-bold">your account</h1>
      {name && <p className="mt-6 font-hand text-4xl leading-none font-bold">{name}</p>}
      {email && (
        <p className={`font-sans text-base text-muted ${name ? 'mt-2' : 'mt-6'}`}>{email}</p>
      )}
      <div className="mt-10">
        <p className="font-hand text-[1.85rem] leading-none font-semibold">appearance</p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <button type="button" aria-pressed={theme === 'light'} className={choiceClass('light')} onClick={() => choose('light')}>
            light
          </button>
          <button type="button" aria-pressed={theme === 'dark'} className={choiceClass('dark')} onClick={() => choose('dark')}>
            dark
          </button>
        </div>
      </div>
      <div className="mt-auto flex flex-col gap-4 pt-8">
        <FormError>{error}</FormError>
        <button
          type="button"
          onClick={logout}
          disabled={busy}
          className="inline-flex h-14 w-full items-center justify-center rounded-full border-2 border-ink font-hand text-[2rem] leading-none font-bold disabled:opacity-50"
        >
          {busy ? 'signing out…' : 'sign out'}
        </button>
      </div>
    </ScreenBody>
  )
}
