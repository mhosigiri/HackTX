const KEY = 'tmm-return-to'

/** Only invitation links are kept, so a stored value can never redirect anywhere else. */
export function isInvitePath(path: string) {
  return /^\/invite\/[0-9a-f-]{36}$/i.test(path)
}

/**
 * Remembers an invitation link across sign-in, sign-up, and the email-confirmation round trip.
 * localStorage survives the confirmation link reopening the app in a fresh tab.
 */
export function rememberReturnTo(path: string) {
  if (!isInvitePath(path)) return
  try {
    localStorage.setItem(KEY, path)
  } catch {
    /* private mode: the link still works if they open it again */
  }
}

export function readReturnTo(): string | null {
  try {
    const path = localStorage.getItem(KEY)
    return path && isInvitePath(path) ? path : null
  } catch {
    return null
  }
}

export function clearReturnTo() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* nothing stored */
  }
}
