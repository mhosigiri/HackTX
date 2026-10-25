import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { cn } from '@/lib/utils'
import { useDisplayMode } from '@/lib/displayMode'

export function ScreenHeader({
  title,
  hideBack,
}: {
  title: string
  hideBack?: boolean
}) {
  const navigate = useNavigate()
  const { mode } = useDisplayMode()
  return (
    <header className="mb-4 flex items-center gap-3">
      {!hideBack && (
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="rounded-full border-2 border-ink bg-paper px-3 py-2 font-hand text-lg leading-none"
        >
          back
        </button>
      )}
      <Link to="/" className="rounded-full border-2 border-ink bg-paper px-3 py-2 font-hand text-lg leading-none">
        home
      </Link>
      <h1 className={cn('font-serif', mode === 'extra_simple' ? 'text-3xl' : 'text-xl')}>
        {title}
      </h1>
    </header>
  )
}

export function BigButton({
  to,
  onClick,
  disabled,
  children,
  primary,
}: {
  to?: string
  onClick?: () => void
  disabled?: boolean
  children: React.ReactNode
  primary?: boolean
}) {
  const { mode } = useDisplayMode()
  const cls = cn(
    'block w-full rounded-full border-2 border-ink px-6 text-center font-hand leading-none font-bold',
    mode === 'extra_simple' ? 'py-5 text-[1.7rem]' : 'py-4 text-[1.45rem]',
    primary ? 'bg-sun text-black' : 'bg-paper text-ink',
    disabled && 'pointer-events-none opacity-40',
  )
  if (to && !disabled) {
    return (
      <Link to={to} className={cls}>
        {children}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={cls}>
      {children}
    </button>
  )
}

export function ReadMore({ text, short = 140 }: { text: string; short?: number }) {
  const { mode } = useDisplayMode()
  const [open, setOpen] = useState(false)
  if (mode !== 'extra_simple' || text.length <= short) return <p>{text}</p>
  return (
    <div>
      <p>{open ? text : `${text.slice(0, short)}…`}</p>
      <button onClick={() => setOpen(!open)} className="text-sm text-muted underline">
        {open ? 'Show less' : 'Read more'}
      </button>
    </div>
  )
}

