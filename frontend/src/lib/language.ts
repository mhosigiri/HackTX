/**
 * Spoken language from "make it yours".
 *
 * Missing contract: GET/PATCH /api/profile accepts display_name, age, and
 * ui_mode only. There is no profile language field, so this stays on the
 * device. POST /api/interviews already takes a per-interview language string;
 * pass getPreferredLanguage() when that flow is wired up.
 */
const KEY = 'tmm-language'

export const LANGUAGES = [
  { id: 'en', label: 'english' },
  { id: 'es', label: 'spanish' },
  { id: 'hi', label: 'hindi' },
] as const

export type LanguageId = (typeof LANGUAGES)[number]['id']

export function getPreferredLanguage(): LanguageId {
  const saved = localStorage.getItem(KEY)
  if (saved === 'en' || saved === 'es' || saved === 'hi') return saved
  return 'en'
}

export function setPreferredLanguage(id: LanguageId) {
  localStorage.setItem(KEY, id)
}
