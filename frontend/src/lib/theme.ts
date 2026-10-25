const KEY = 'tmm-theme'

export type ThemeChoice = 'light' | 'dark'

export function storedTheme(): ThemeChoice | null {
  const saved = localStorage.getItem(KEY)
  return saved === 'light' || saved === 'dark' ? saved : null
}

export function activeTheme(): ThemeChoice {
  const saved = storedTheme()
  if (saved) return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(choice: ThemeChoice) {
  document.documentElement.dataset.theme = choice
  localStorage.setItem(KEY, choice)
}
