import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import {
  BackLink,
  FormError,
  PersonMark,
  ScreenBody,
  YellowButton,
} from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'
import { AgeSlider, LanguageSelect } from '@/components/ui/fields'
import { formatApiError } from '@/lib/apiError'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useDisplayMode } from '@/lib/displayMode'
import { getPreferredLanguage, setPreferredLanguage, type LanguageId } from '@/lib/language'
import { clearDisplayName, nameForProfile } from '@/lib/pendingProfile'
import { profileKey, useProfile } from '@/lib/profile'

export function Onboarding() {
  useScreenTitle('make it yours')
  const navigate = useNavigate()
  const { session, signOut } = useAuth()
  const { adopt } = useDisplayMode()
  const profile = useProfile()
  const qc = useQueryClient()
  const savedAge = typeof profile.data?.age === 'number' ? profile.data.age : null
  const [draftAge, setDraftAge] = useState<number | null>(null)
  const age = draftAge ?? savedAge ?? 24
  const [language, setLanguage] = useState<LanguageId>(() => getPreferredLanguage())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function finish(e: FormEvent) {
    e.preventDefault()
    if (!session) {
      setError('create an account first.')
      return
    }
    setBusy(true)
    setError(null)
    setPreferredLanguage(language)
    const displayName = nameForProfile(session.user.user_metadata, profile.data?.display_name)
    const { data, error: apiError } = await api.PATCH('/api/profile', {
      body: {
        age,
        ...(displayName ? { display_name: displayName } : {}),
      },
    })
    setBusy(false)
    if (apiError || !data) {
      setError(formatApiError(apiError, 'we could not save that. try again.'))
      return
    }
    clearDisplayName()
    adopt({ age: data.age, ui_mode: data.ui_mode })
    qc.setQueryData(profileKey(session.user.id), data)
    navigate('/', { replace: true })
  }

  return (
    <ScreenBody screen="onboarding" className="pt-6 pb-5">
      <BackLink to="/sign-up" state={{ editing: true }} />
      <h1 className="mt-4 font-hand text-5xl leading-none font-bold">make it yours</h1>
      <div className="mt-4 flex justify-center">
        <PersonMark />
      </div>
      <form onSubmit={finish} className="mt-6 flex flex-1 flex-col gap-6">
        <AgeSlider
          value={age}
          onChange={setDraftAge}
        />
        <LanguageSelect
          value={language}
          onChange={(next) => {
            setLanguage(next)
            setPreferredLanguage(next)
          }}
        />
        <div className="mt-auto flex flex-col gap-3 pt-5">
          <FormError>{error}</FormError>
          <YellowButton type="submit" disabled={busy}>
            {busy ? 'saving…' : 'finish →'}
          </YellowButton>
          <button
            type="button"
            className="font-hand text-[1.6rem] leading-none font-semibold"
            onClick={async () => {
              try {
                await signOut()
              } catch {
                /* leave the screen either way */
              }
              clearDisplayName()
              qc.clear()
              navigate('/', { replace: true })
            }}
          >
            sign out
          </button>
        </div>
      </form>
    </ScreenBody>
  )
}
