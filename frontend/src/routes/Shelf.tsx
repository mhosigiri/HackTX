import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { api } from '@/lib/api'
import { useFamily } from '@/lib/family'

export function Shelf() {
  const { data: family, isLoading } = useFamily()
  const heirlooms = useQuery({
    queryKey: ['heirlooms', family?.id],
    enabled: !!family,
    queryFn: async () =>
      (await api.GET('/api/heirlooms', { params: { query: { family_id: family!.id } } })).data ??
      [],
  })

  if (isLoading) return null
  if (!family) return <CreateFamily />

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="font-serif text-3xl">{family.name}</h1>
        <Link to="/family" className="text-sm text-muted">
          Family
        </Link>
      </header>
      <div className="grid grid-cols-2 gap-4">
        <Link
          to="/capture"
          className="flex aspect-square items-center justify-center rounded-xl border-2 border-dashed border-ink/20 text-muted"
        >
          + Add an heirloom
        </Link>
        {heirlooms.data?.map((h) => (
          <Link key={h.id} to={`/h/${h.id}`} className="overflow-hidden rounded-xl bg-white shadow">
            {h.cover_url && <img src={h.cover_url} className="aspect-square w-full object-cover" />}
            <p className="p-3 font-serif">{h.title ?? 'Untitled'}</p>
          </Link>
        ))}
      </div>
    </main>
  )
}

function CreateFamily() {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [yourName, setYourName] = useState('')
  const create = useMutation({
    mutationFn: () => api.POST('/api/families', { body: { name, your_name: yourName } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['families'] }),
  })

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-3 px-4">
      <h1 className="font-serif text-5xl">start your family</h1>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Family name"
        className="rounded-lg border border-ink/20 bg-white px-4 py-3"
      />
      <input
        value={yourName}
        onChange={(e) => setYourName(e.target.value)}
        placeholder="Your name"
        className="rounded-lg border border-ink/20 bg-white px-4 py-3"
      />
      <button
        disabled={!name || !yourName || create.isPending}
        onClick={() => create.mutate()}
        className="rounded-lg bg-ink px-4 py-3 text-paper disabled:opacity-40"
      >
        Create
      </button>
    </main>
  )
}
