import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { BootScreen, FormError, HandLink, ScreenBody, YellowButton } from '@/components/ui/chrome'
import { api, type Schemas } from '@/lib/api'
import { formatApiError } from '@/lib/apiError'
import { useAuth } from '@/lib/auth'
import { useProfile } from '@/lib/profile'
import { initials, kindLabel, possessive } from '@/lib/relations'
import { clearReturnTo, readReturnTo, rememberReturnTo } from '@/lib/returnTo'
import { useScreenTitle } from '@/lib/useScreenTitle'

class InviteLoadError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function InviteResponse() {
  useScreenTitle('invitation')
  const { inviteId = '' } = useParams()
  const path = `/invite/${inviteId}`
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { session, signOut } = useAuth()
  const profile = useProfile()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'accept' | 'decline' | null>(null)

  useEffect(() => {
    if (readReturnTo() === path) clearReturnTo()
  }, [path])

  const invite = useQuery({
    queryKey: ['invite', inviteId],
    retry: false,
    queryFn: async () => {
      const { data, error: apiError, response } = await api.GET('/api/invites/{invite_id}', {
        params: { path: { invite_id: inviteId } },
      })
      if (apiError || !data) {
        throw new InviteLoadError(
          response.status,
          formatApiError(apiError, 'we could not load that invitation.'),
        )
      }
      return data
    },
  })

  async function respond(action: 'accept' | 'decline') {
    setBusy(action)
    setError(null)
    const route =
      action === 'accept' ? '/api/invites/{invite_id}/accept' : '/api/invites/{invite_id}/decline'
    const { data, error: apiError } = await api.POST(route, {
      params: { path: { invite_id: inviteId } },
    })
    setBusy(null)
    if (apiError || !data) {
      setError(formatApiError(apiError, 'that did not work. try again.'))
      invite.refetch()
      return
    }
    qc.setQueryData(['invite', inviteId], data)
    if (action === 'accept') {
      qc.invalidateQueries({ queryKey: ['families'] })
      qc.invalidateQueries({ queryKey: ['tree'] })
      qc.invalidateQueries({ queryKey: ['invites'] })
    }
  }

  async function switchAccount() {
    rememberReturnTo(path)
    try {
      await signOut()
    } catch {
      /* still let them pick another account */
    }
    qc.clear()
    navigate('/sign-in', { replace: true })
  }

  if (invite.isLoading) return <BootScreen />

  if (invite.isError) {
    const status = invite.error instanceof InviteLoadError ? invite.error.status : 0
    return (
      <ScreenBody screen="invite-error">
        <h1 className="font-hand text-5xl leading-none font-bold">
          {status === 403 ? 'not for this account' : 'invitation'}
        </h1>
        <p className="mt-4 font-sans text-lg leading-snug">
          {status === 404 ? 'we could not find that invitation. ask for a new link.' : invite.error.message}
        </p>
        {status === 403 && session?.user.email && (
          <p className="mt-2 font-sans text-base text-muted">you are signed in as {session.user.email}.</p>
        )}
        <div className="mt-auto flex flex-col gap-4 pt-8">
          {status === 403 ? (
            <YellowButton onClick={switchAccount}>sign in with that email →</YellowButton>
          ) : status !== 404 ? (
            <YellowButton onClick={() => invite.refetch()}>try again →</YellowButton>
          ) : null}
          <HandLink to="/">home</HandLink>
        </div>
      </ScreenBody>
    )
  }

  const data = invite.data as Schemas['Invite']
  const inviter = data.inviter_name || 'someone'
  const role = `${possessive(data.anchor_name)} ${kindLabel(data.kind)}`

  return (
    <ScreenBody screen="invite-response">
      <h1 className="font-hand text-5xl leading-none font-bold">{inviter} invited you</h1>
      <div className="mt-8 flex items-center justify-center gap-3" aria-hidden>
        <Avatar label={data.anchor_name} name={data.anchor_name} />
        <span className="h-0.5 w-10 bg-ink" />
        <Avatar label="you" name={profile.data?.display_name || session?.user.email || 'you'} highlight />
      </div>
      <p className="mt-8 text-center font-hand text-[2.3rem] leading-[0.95] font-bold">join as {role}</p>
      <p className="mt-4 text-center font-sans text-base leading-snug" data-testid="invite-meaning">
        accepting adds you to “{data.family_name}” as {role}. {data.anchor_name} is your{' '}
        {reverse(data.kind)}.
      </p>

      <div className="mt-auto flex flex-col gap-3 pt-8">
        <FormError>{error}</FormError>
        {data.status === 'pending' && data.can_respond && (
          <>
            <YellowButton onClick={() => respond('accept')} disabled={busy !== null}>
              {busy === 'accept' ? 'joining…' : 'accept →'}
            </YellowButton>
            <button
              type="button"
              onClick={() => respond('decline')}
              disabled={busy !== null}
              className="inline-flex h-14 w-full items-center justify-center rounded-full border-2 border-ink font-hand text-[2rem] leading-none font-bold disabled:opacity-50"
            >
              {busy === 'decline' ? 'declining…' : 'decline'}
            </button>
          </>
        )}
        {data.status === 'pending' && !data.can_respond && (
          <p className="text-center font-sans text-base">waiting for {data.email} to answer.</p>
        )}
        {data.status === 'accepted' && (
          <>
            <p className="text-center font-sans text-lg">you are in the family.</p>
            <YellowButton to="/family">open family tree →</YellowButton>
          </>
        )}
        {data.status === 'declined' && (
          <>
            <p className="text-center font-sans text-lg">this invitation was declined.</p>
            <HandLink to="/">home</HandLink>
          </>
        )}
      </div>
    </ScreenBody>
  )
}

/** What the anchor is to the recipient, given what the recipient is to the anchor. */
function reverse(kind: Schemas['Invite']['kind']) {
  if (kind === 'parent') return 'child'
  if (kind === 'child') return 'parent'
  return kindLabel(kind)
}

function Avatar({ label, name, highlight }: { label: string; name: string; highlight?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span
        className={`grid size-20 place-items-center rounded-full border-2 border-ink font-hand text-[2.2rem] leading-none font-bold ${
          highlight ? 'bg-sun text-black' : ''
        }`}
      >
        {initials(name)}
      </span>
      <span className="font-hand text-[1.6rem] leading-none font-semibold">{label}</span>
    </div>
  )
}
