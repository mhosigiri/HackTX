const NAME_KEY = 'tmm-pending-name'

export function stashDisplayName(name: string) {
  localStorage.setItem(NAME_KEY, name.trim())
}

export function readDisplayName(): string {
  return localStorage.getItem(NAME_KEY)?.trim() ?? ''
}

export function clearDisplayName() {
  localStorage.removeItem(NAME_KEY)
}

/**
 * Name to copy onto PATCH /api/profile.
 * user_metadata.display_name is a label the person typed at sign-up. It is
 * not used for authorization.
 */
export function nameForProfile(metadata: unknown, profileName?: string | null): string {
  const stashed = readDisplayName()
  if (stashed) return stashed
  if (metadata && typeof metadata === 'object' && 'display_name' in metadata) {
    const value = (metadata as { display_name?: unknown }).display_name
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return profileName?.trim() ?? ''
}
