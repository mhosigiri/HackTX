import { useEffect } from 'react'

export function useScreenTitle(title: string) {
  useEffect(() => {
    document.title = title === 'tell me more' ? title : `${title} · tell me more`
  }, [title])
}
