import type { Schemas } from '@/lib/api'

export type InviteKind = Schemas['CreateInvite']['kind']

/** `kind` is always the invited person relative to the anchor: parent = the anchor's parent. */
export const INVITE_KINDS: { id: InviteKind; label: string }[] = [
  { id: 'parent', label: 'parent' },
  { id: 'child', label: 'child' },
  { id: 'spouse', label: 'spouse or partner' },
  { id: 'sibling', label: 'sibling' },
]

export function kindLabel(kind: InviteKind) {
  return INVITE_KINDS.find((k) => k.id === kind)?.label ?? kind
}

export function possessive(name: string) {
  return /s$/i.test(name) ? `${name}'` : `${name}'s`
}

/** "your parent" when the anchor is you, otherwise "grandpa's parent". */
export function relationTo(kind: InviteKind, anchorName: string, anchorIsYou: boolean) {
  return `${anchorIsYou ? 'your' : possessive(anchorName)} ${kindLabel(kind)}`
}

export function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}
