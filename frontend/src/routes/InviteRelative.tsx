import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useParams } from 'react-router'
import {
  BackLink,
  BootScreen,
  FormError,
  HandLink,
  ScreenBody,
  YellowButton,
} from '@/components/ui/chrome'
import { TextField } from '@/components/ui/fields'
import { api, type Schemas } from '@/lib/api'
import { formatApiError } from '@/lib/apiError'
import { copyText, inviteLink } from '@/lib/clipboard'
import { useFamily, useFamilyTree } from '@/lib/family'
import {
  INVITE_KINDS,
  initials,
  kindLabel,
  possessive,
  relationTo,
  type InviteKind,
} from '@/lib/relations'
import { useScreenTitle } from '@/lib/useScreenTitle'

export function InviteRelative() {
  useScreenTitle('invite a relative')
  const { personId } = useParams()
  const qc = useQueryClient()
  const family = useFamily()
  const tree = useFamilyTree(family.data?.id)
  const [kind, setKind] = useState<InviteKind>('parent')
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<Schemas['Invite'] | null>(null)
  const [copied, setCopied] = useState<'yes' | 'failed' | null>(null)

  if (family.isLoading || tree.isLoading) return <BootScreen />
  const anchor = tree.data?.people.find((p) => p.id === personId)
  if (!family.data || !tree.data || !anchor) {
    return (
      <ScreenBody screen="invite-missing">
        <BackLink to="/family" />
        <h1 className="mt-6 font-hand text-5xl leading-none font-bold">add a relative</h1>
        <p className="mt-4 font-sans text-lg leading-snug">
          {tree.error?.message ?? family.error?.message ?? 'we could not find that person in your family.'}
        </p>
      </ScreenBody>
    )
  }

  const familyId = family.data.id
  const anchorIsYou = anchor.id === tree.data.me
  const owner = anchorIsYou ? 'your' : possessive(anchor.display_name)
  const phrase = relationTo(kind, anchor.display_name, anchorIsYou)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!email.includes('@')) {
      setError('add their email address.')
      return
    }
    setBusy(true)
    const { data, error: apiError } = await api.POST('/api/families/{family_id}/invites', {
      params: { path: { family_id: familyId } },
      body: { anchor_person_id: anchor!.id, kind, email: email.trim() },
    })
    setBusy(false)
    if (apiError || !data) {
      setError(formatApiError(apiError, 'we could not create that invitation. try again.'))
      return
    }
    qc.invalidateQueries({ queryKey: ['invites', familyId] })
    setSent(data)
  }

  if (sent) {
    const link = inviteLink(sent.id)
    return (
      <ScreenBody screen="invite-ready">
        <BackLink to="/family" />
        <h1 className="mt-6 font-hand text-5xl leading-none font-bold">invitation ready</h1>
        <p className="mt-4 rounded-2xl border-2 border-sun px-4 py-3 font-sans text-base leading-snug">
          no email was sent. copy this link and send it to {sent.email} yourself.
        </p>
        <p className="mt-4 font-sans text-lg leading-snug">
          once they accept, they join the tree as {relationTo(sent.kind, sent.anchor_name, anchorIsYou)}.
        </p>
        <p className="mt-5 rounded-2xl border-2 border-ink px-4 py-3 font-sans text-sm break-all" data-testid="invite-link">
          {link}
        </p>
        <div className="mt-auto flex flex-col gap-4 pt-8">
          <YellowButton onClick={async () => setCopied((await copyText(link)) ? 'yes' : 'failed')}>
            {copied === 'yes' ? 'copied ✓' : 'copy invitation link'}
          </YellowButton>
          {copied === 'failed' && <FormError>copy did not work. select the link above instead.</FormError>}
          <HandLink to="/family">back to the tree</HandLink>
        </div>
      </ScreenBody>
    )
  }

  return (
    <ScreenBody screen="invite-relative" className="pt-6 pb-5">
      <BackLink to="/family" />
      <h1 className="mt-4 font-hand text-5xl leading-none font-bold">
        add {owner} {kindLabel(kind)}
      </h1>
      <div className="mt-5 flex flex-col items-center gap-2">
        <span
          className={`grid size-20 place-items-center rounded-full border-2 border-ink font-hand text-[2.2rem] leading-none font-bold ${
            anchorIsYou ? 'bg-sun text-black' : ''
          }`}
          aria-hidden
        >
          {initials(anchor.display_name)}
        </span>
        <p className="font-hand text-[1.7rem] leading-none font-semibold">
          {anchorIsYou ? `you (${anchor.display_name})` : anchor.display_name}
        </p>
      </div>
      <form onSubmit={submit} className="mt-5 flex flex-1 flex-col gap-4" noValidate>
        <fieldset>
          <legend className="font-hand text-[1.85rem] leading-none font-semibold">relationship</legend>
          <div className="mt-2 grid grid-cols-2 gap-2" role="radiogroup">
            {INVITE_KINDS.map((option) => (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={kind === option.id}
                onClick={() => setKind(option.id)}
                className={`h-11 rounded-full border-2 border-ink font-hand text-[1.45rem] leading-none font-semibold ${
                  kind === option.id ? 'bg-sun text-black' : ''
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>
        <p className="rounded-2xl border-2 border-dashed border-ink px-4 py-3 font-sans text-base leading-snug" data-testid="invite-direction">
          the person you invite joins as <strong>{phrase}</strong>.
        </p>
        <TextField
          label="their email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="off"
          value={email}
          onChange={setEmail}
        />
        <div className="mt-auto flex flex-col gap-3 pt-4">
          <FormError>{error}</FormError>
          <YellowButton type="submit" disabled={busy}>
            {busy ? 'creating…' : 'create invitation →'}
          </YellowButton>
          <p className="text-center font-sans text-sm text-muted">
            you will get a link to share. no email is sent.
          </p>
        </div>
      </form>
    </ScreenBody>
  )
}
