export async function copyText(text: string): Promise<boolean> {
  try {
    // Some embedded browsers leave the permission prompt unanswered; don't wait on it forever.
    await Promise.race([
      navigator.clipboard.writeText(text),
      new Promise((_, reject) => setTimeout(() => reject(new Error('clipboard timeout')), 1500)),
    ])
    return true
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    area.remove()
    return ok
  }
}

export function inviteLink(inviteId: string) {
  return `${window.location.origin}/invite/${inviteId}`
}
