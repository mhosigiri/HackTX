import { useCallback, useContext, useEffect, useRef, useState, createContext, type ReactNode } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { supabaseConfigured } from '@/lib/supabase'

export type DisplayMode = 'regular' | 'simplified' | 'extra_simple'

const KEY = 'tmm-ui-mode'

export function isDisplayMode(value: string | null | undefined): value is DisplayMode {
  return value === 'regular' || value === 'simplified' || value === 'extra_simple'
}

export function defaultModeForAge(age: number | null | undefined): DisplayMode {
  if (age == null) return 'simplified'
  if (age < 18) return 'regular'
  if (age <= 50) return 'simplified'
  return 'extra_simple'
}

type ProfilePatch = { age?: number | null; ui_mode?: string | null }

const Ctx = createContext<{
  mode: DisplayMode
  age: number | null
  setMode: (m: DisplayMode) => void
  setAge: (a: number | null) => void
  adopt: (next: ProfilePatch) => void
}>({
  mode: 'simplified',
  age: null,
  setMode: () => {},
  setAge: () => {},
  adopt: () => {},
})

export function DisplayModeProvider({ children }: { children: ReactNode }) {
  const { ready, session } = useAuth()
  const userId = session?.user.id
  const gen = useRef(0)
  const [mode, setModeState] = useState<DisplayMode>(() => {
    const saved = localStorage.getItem(KEY)
    return saved === 'regular' || saved === 'extra_simple' ? saved : 'simplified'
  })
  const [storedAge, setStoredAge] = useState<{ userId: string; age: number | null } | null>(null)
  const age = storedAge && storedAge.userId === userId ? storedAge.age : null

  useEffect(() => {
    if (!ready || !userId || !supabaseConfigured) return
    const id = ++gen.current
    api
      .GET('/api/profile')
      .then(({ data }) => {
        if (id !== gen.current || !data) return
        if (typeof data.age === 'number') setStoredAge({ userId, age: data.age })
        if (isDisplayMode(data.ui_mode)) {
          setModeState(data.ui_mode)
          localStorage.setItem(KEY, data.ui_mode)
        }
      })
      .catch(() => {})
  }, [ready, userId])

  const setMode = useCallback((m: DisplayMode) => {
    gen.current += 1
    setModeState(m)
    localStorage.setItem(KEY, m)
    api.PATCH('/api/profile', { body: { ui_mode: m } }).catch(() => {})
  }, [])

  const setAge = useCallback((a: number | null) => {
    gen.current += 1
    if (userId) setStoredAge({ userId, age: a })
    if (a != null) {
      const next = defaultModeForAge(a)
      setModeState(next)
      localStorage.setItem(KEY, next)
    }
  }, [userId])

  const adopt = useCallback((next: ProfilePatch) => {
    gen.current += 1
    if (typeof next.age === 'number' && userId) setStoredAge({ userId, age: next.age })
    if (isDisplayMode(next.ui_mode)) {
      setModeState(next.ui_mode)
      localStorage.setItem(KEY, next.ui_mode)
    }
  }, [userId])

  return <Ctx.Provider value={{ mode, age, setMode, setAge, adopt }}>{children}</Ctx.Provider>
}

export function useDisplayMode() {
  return useContext(Ctx)
}

export function headingSize(mode: DisplayMode): string {
  if (mode === 'extra_simple') return 'text-4xl'
  if (mode === 'regular') return 'text-2xl'
  return 'text-3xl'
}
