import type { ReactNode } from 'react'

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 72 72"
      className="size-16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  )
}

export function CaptureIcon() {
  return (
    <Glyph>
      <path d="M26 22 30 16h12l4 6" />
      <rect x="14" y="22" width="44" height="32" rx="8" />
      <circle cx="36" cy="38" r="8" />
    </Glyph>
  )
}

export function DatesIcon() {
  return (
    <Glyph>
      <rect x="14" y="16" width="44" height="40" rx="6" />
      <path d="M14 28h44" />
      <path d="M26 12v10M46 12v10" />
      <path d="M26 40h8M38 40h8M26 48h8" />
    </Glyph>
  )
}

export function TreeIcon() {
  return (
    <Glyph>
      <circle cx="36" cy="16" r="7" />
      <path d="M36 23v10M18 42h36M18 42v6M54 42v6" />
      <circle cx="18" cy="54" r="6" />
      <circle cx="54" cy="54" r="6" />
    </Glyph>
  )
}

export function MemoriesIcon() {
  return (
    <Glyph>
      <circle cx="24" cy="24" r="7" />
      <path d="M12 52c1.4-10 8-14 12-14s10.6 4 12 14" />
      <circle cx="48" cy="26" r="7" />
      <path d="M36 54c1.4-10 8-14 12-14s10.6 4 12 14" />
    </Glyph>
  )
}

export function AvailabilityIcon() {
  return (
    <Glyph>
      <rect x="14" y="16" width="44" height="40" rx="6" />
      <path d="M14 28h44" />
      <path d="M26 12v10M46 12v10" />
      <circle cx="28" cy="42" r="3" fill="currentColor" stroke="none" />
      <circle cx="36" cy="42" r="3" fill="#f5c400" stroke="none" />
      <circle cx="44" cy="42" r="3" fill="currentColor" stroke="none" />
    </Glyph>
  )
}

export function TimelineIcon() {
  return (
    <Glyph>
      <path d="M28 12v48" />
      <circle cx="28" cy="18" r="4" fill="var(--paper)" />
      <path d="M32 18h16" />
      <circle cx="28" cy="36" r="4" fill="var(--paper)" />
      <path d="M32 36h16" />
      <circle cx="28" cy="54" r="4" fill="var(--paper)" />
      <path d="M32 54h16" />
    </Glyph>
  )
}
