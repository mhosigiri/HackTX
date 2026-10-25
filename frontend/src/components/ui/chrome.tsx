import type { ReactNode } from 'react'
import { Link, Outlet } from 'react-router'
import { readReturnTo } from '@/lib/returnTo'
import { cn } from '@/lib/utils'

export function FrameLayout() {
  return (
    <PhoneFrame>
      <div className="flex min-h-dvh flex-1 flex-col sm:min-h-full">
        <Outlet />
      </div>
    </PhoneFrame>
  )
}

export function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-1 justify-center bg-stage sm:h-dvh sm:items-center sm:overflow-hidden">
      <div className="flex min-h-dvh w-full flex-col bg-paper text-ink sm:my-4 sm:h-[min(880px,calc(100dvh-2rem))] sm:max-w-[400px] sm:min-h-0 sm:overflow-y-auto sm:rounded-[2rem] sm:border-2 sm:border-ink">
        {children}
      </div>
    </div>
  )
}

export function ScreenBody({
  children,
  className,
  screen,
}: {
  children: ReactNode
  className?: string
  screen?: string
}) {
  return (
    <main
      data-screen={screen}
      className={cn('flex min-h-dvh flex-1 flex-col px-6 pt-8 pb-8 sm:min-h-full', className)}
    >
      {children}
    </main>
  )
}

export function BootScreen() {
  return (
    <div className="grid min-h-dvh flex-1 place-items-center sm:min-h-full" role="status">
      <p className="font-hand text-5xl leading-none font-bold">tell me more</p>
    </div>
  )
}

export function BackLink({ to, state }: { to: string; state?: unknown }) {
  return (
    <Link
      to={to}
      state={state}
      aria-label="Back"
      className="w-fit font-hand text-4xl leading-none font-bold"
    >
      ←
    </Link>
  )
}

const yellowClass =
  'inline-flex h-14 w-full items-center justify-center rounded-full border-2 border-ink bg-sun px-6 font-hand text-[2rem] leading-none font-bold text-black transition hover:brightness-95 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50'

export function YellowButton({
  children,
  disabled,
  type = 'button',
  onClick,
  to,
}: {
  children: ReactNode
  disabled?: boolean
  type?: 'button' | 'submit'
  onClick?: () => void
  to?: string
}) {
  if (to && !disabled) {
    return (
      <Link to={to} className={yellowClass}>
        {children}
      </Link>
    )
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={yellowClass}>
      {children}
    </button>
  )
}

export function HandLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="block text-center font-hand text-[1.85rem] leading-none font-semibold">
      {children}
    </Link>
  )
}

export function FormError({ children }: { children?: ReactNode }) {
  if (!children) return null
  return (
    <p role="alert" className="text-center font-sans text-sm text-ink">
      {children}
    </p>
  )
}

/** Shown on the signed-out screens while an invitation link is waiting to reopen. */
export function InviteNote({ className }: { className?: string }) {
  if (!readReturnTo()) return null
  return (
    <p
      className={cn('rounded-2xl border-2 border-sun px-4 py-2.5 text-left font-sans text-sm leading-snug', className)}
      data-testid="invite-note"
    >
      you have a family invitation. sign in or create an account with the email it was sent to.
    </p>
  )
}

export function PersonMark() {
  return (
    <div className="grid size-14 place-items-center rounded-full border-2 border-ink" aria-hidden>
      <svg viewBox="0 0 24 24" className="size-8" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="8" r="3.2" />
        <path d="M5.5 19.5c1.2-3.4 3.5-5 6.5-5s5.3 1.6 6.5 5" strokeLinecap="round" />
      </svg>
    </div>
  )
}
