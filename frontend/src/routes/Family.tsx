import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent } from 'react'
import { FamilyTreeView } from '@/components/family/FamilyTreeView'
import { BackLink, BootScreen, FormError, ScreenBody, YellowButton } from '@/components/ui/chrome'
import { TextField } from '@/components/ui/fields'
import { TreeIcon } from '@/components/ui/sketchIcons'
import { api, type Schemas } from '@/lib/api'
import { formatApiError } from '@/lib/apiError'
import { useAuth } from '@/lib/auth'
import { copyText, inviteLink } from '@/lib/clipboard'
import { useFamily, useFamilyInvites, useFamilyTree } from '@/lib/family'
import { useProfile } from '@/lib/profile'
import { kindLabel, possessive, relationTo } from '@/lib/relations'
import { layoutTree } from '@/lib/treeLayout'
import { useScreenTitle } from '@/lib/useScreenTitle'

type Family = Schemas['Family']
type Tree = Schemas['FamilyTree']
type Invite = Schemas['Invite']

export function Family() {
  useScreenTitle('family tree')
  const family = useFamily()
  if (family.isLoading) return <BootScreen />
  if (family.isError) {
    return (
      <ScreenBody screen="family-error">
        <BackLink to="/" />
        <h1 className="mt-6 font-hand text-5xl leading-none font-bold">family tree</h1>
        <p className="mt-4 font-sans text-lg leading-snug">{family.error.message}</p>
        <div className="mt-auto">
          <YellowButton onClick={() => family.refetch()}>try again →</YellowButton>
        </div>
      </ScreenBody>
    )
  }
  if (!family.data) return <CreateFamily />
  return <FamilyTreeScreen family={family.data} />
}

function CreateFamily() {
  const qc = useQueryClient()
  const { session } = useAuth()
  const profile = useProfile()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('add a family name.')
      return
    }
    const yourName =
      profile.data?.display_name?.trim() || session?.user.email?.split('@')[0] || 'me'
    setBusy(true)
    const { data, error: apiError } = await api.POST('/api/families', {
      body: { name: name.trim(), your_name: yourName },
    })
    setBusy(false)
    if (apiError || !data) {
      setError(formatApiError(apiError, 'we could not create your family. try again.'))
      return
    }
    qc.setQueryData(['families'], [data])
    qc.invalidateQueries({ queryKey: ['families'] })
  }

  return (
    <ScreenBody screen="family-setup">
      <BackLink to="/" />
      <h1 className="mt-6 font-hand text-5xl leading-none font-bold">family tree</h1>
      <div className="mt-8 flex justify-center">
        <TreeIcon />
      </div>
      <p className="mt-6 font-sans text-lg leading-snug">
        start your family so you can share stories, memories, and availability together.
      </p>
      <form onSubmit={submit} className="mt-6 flex flex-1 flex-col gap-4" noValidate>
        <TextField label="family name" name="family-name" value={name} onChange={setName} />
        <div className="mt-auto flex flex-col gap-3 pt-5">
          <FormError>{error}</FormError>
          <YellowButton type="submit" disabled={busy}>
            {busy ? 'creating…' : 'create a family →'}
          </YellowButton>
        </div>
      </form>
    </ScreenBody>
  )
}

function relationToMe(tree: Tree, id: string): string | null {
  const me = tree.me
  if (!me || id === me) return null
  for (const e of tree.relationships) {
    if (e.kind === 'parent') {
      if (e.a === id && e.b === me) return `your ${kindLabel('parent')}`
      if (e.a === me && e.b === id) return `your ${kindLabel('child')}`
    } else if ((e.a === id && e.b === me) || (e.a === me && e.b === id)) {
      return `your ${kindLabel(e.kind === 'spouse' ? 'spouse' : 'sibling')}`
    }
  }
  return null
}

function FamilyTreeScreen({ family }: { family: Family }) {
  const tree = useFamilyTree(family.id)
  const invites = useFamilyInvites(family.id)
  const [picked, setPicked] = useState<string | null>(null)
  const layout = useMemo(() => (tree.data ? layoutTree(tree.data) : null), [tree.data])
  const selectedId = picked ?? tree.data?.me ?? null
  const selected = tree.data?.people.find((p) => p.id === selectedId) ?? null
  const pending = invites.data?.filter((i) => i.status === 'pending') ?? []
  const declined = invites.data?.filter((i) => i.status === 'declined') ?? []

  return (
    <ScreenBody screen="family-tree" className="pt-6">
      <BackLink to="/" />
      <h1 className="mt-4 font-hand text-5xl leading-none font-bold">family tree</h1>
      <p className="mt-1 font-sans text-base text-muted">{family.name}</p>

      <div className="mt-5">
        {tree.isLoading && <p className="font-sans text-base text-muted">loading your tree…</p>}
        {tree.isError && (
          <div className="flex flex-col gap-3">
            <FormError>{tree.error.message}</FormError>
            <YellowButton onClick={() => tree.refetch()}>try again →</YellowButton>
          </div>
        )}
        {tree.data && layout && (
          <FamilyTreeView
            layout={layout}
            meId={tree.data.me ?? null}
            selectedId={selectedId}
            onSelect={setPicked}
          />
        )}
      </div>

      {layout && layout.unplaced.length > 0 && (
        <section className="mt-6">
          <h2 className="font-hand text-[1.85rem] leading-none font-semibold">not in the tree yet</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {layout.unplaced.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPicked(p.id)}
                aria-pressed={p.id === selectedId}
                className={`rounded-full border-2 border-ink px-4 py-1.5 font-hand text-[1.4rem] leading-none font-semibold ${
                  p.id === selectedId ? 'bg-sun text-black' : ''
                }`}
              >
                {p.display_name}
              </button>
            ))}
          </div>
        </section>
      )}

      {tree.data && selected && (
        <PersonDetails tree={tree.data} person={selected} pending={pending} />
      )}

      <section className="mt-8" aria-labelledby="pending-heading">
        <h2 id="pending-heading" className="font-hand text-[1.85rem] leading-none font-semibold">
          pending invitations
        </h2>
        {invites.isError && <FormError>{invites.error.message}</FormError>}
        {invites.data && pending.length === 0 && (
          <p className="mt-2 font-sans text-base text-muted">no one is waiting to answer.</p>
        )}
        {pending.length > 0 && (
          <>
            <p className="mt-2 font-sans text-sm text-muted">
              no email is sent. share each link yourself.
            </p>
            <ul className="mt-3 flex flex-col gap-3">
              {pending.map((invite) => (
                <InviteRow key={invite.id} invite={invite} me={tree.data?.me ?? null} />
              ))}
            </ul>
          </>
        )}
        {declined.length > 0 && (
          <>
            <h3 className="mt-6 font-hand text-[1.6rem] leading-none font-semibold text-muted">declined</h3>
            <ul className="mt-2 flex flex-col gap-1">
              {declined.map((invite) => (
                <li key={invite.id} className="font-sans text-sm text-muted">
                  {invite.email} · as {relationTo(invite.kind, invite.anchor_name, invite.anchor_person_id === tree.data?.me)}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </ScreenBody>
  )
}

function PersonDetails({
  tree,
  person,
  pending,
}: {
  tree: Tree
  person: Schemas['Person']
  pending: Invite[]
}) {
  const isMe = person.id === tree.me
  const hasAccount = tree.member_person_ids.includes(person.id)
  const waiting = pending.filter((i) => i.anchor_person_id === person.id).length
  const relation = relationToMe(tree, person.id)
  return (
    <section className="mt-6 rounded-[1.6rem] border-2 border-ink p-4" aria-label={`${person.display_name} details`}>
      <p className="font-hand text-4xl leading-none font-bold">{isMe ? 'you' : person.display_name}</p>
      <p className="mt-2 font-sans text-base">
        {isMe ? person.display_name : relation ?? `in this family`}
        {person.birth_year ? ` · born ${person.birth_year}` : ''}
      </p>
      <p className="mt-1 font-sans text-sm text-muted">
        {hasAccount ? 'on tell me more' : 'added by name, no account yet'}
        {waiting > 0 ? ` · ${waiting} pending invitation${waiting === 1 ? '' : 's'}` : ''}
      </p>
      <div className="mt-4">
        <YellowButton to={`/family/invite/${person.id}`}>
          {isMe ? 'add your relative →' : `add ${possessive(person.display_name)} relative →`}
        </YellowButton>
      </div>
    </section>
  )
}

function InviteRow({ invite, me }: { invite: Invite; me: string | null }) {
  const [copied, setCopied] = useState<'yes' | 'failed' | null>(null)
  const link = inviteLink(invite.id)
  return (
    <li className="rounded-2xl border-2 border-dashed border-ink px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-sans text-base">{invite.email}</p>
          <p className="font-sans text-sm text-muted">
            as {relationTo(invite.kind, invite.anchor_name, invite.anchor_person_id === me)} · pending
          </p>
        </div>
        <button
          type="button"
          onClick={async () => setCopied((await copyText(link)) ? 'yes' : 'failed')}
          className="shrink-0 rounded-full border-2 border-ink px-3 py-1.5 font-hand text-[1.3rem] leading-none font-semibold"
        >
          {copied === 'yes' ? 'copied ✓' : 'copy link'}
        </button>
      </div>
      {copied === 'failed' && (
        <p className="mt-2 font-sans text-xs break-all select-all">copy did not work. select this link: {link}</p>
      )}
    </li>
  )
}
