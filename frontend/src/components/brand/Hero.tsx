/**
 * Welcome illustration.
 * Drop a png, jpg, webp, or svg into src/image/ and it replaces this drawing.
 * A filename containing "hero" or "welcome" wins when several images are there.
 */
const heroModules = import.meta.glob('../../image/*.{png,jpg,jpeg,webp,svg,avif}', {
  eager: true,
  import: 'default',
}) as Record<string, string>

function pickHero(files: Record<string, string>) {
  const entries = Object.entries(files)
  const preferred = entries.find(([path]) => /hero|welcome/i.test(path))
  return (preferred ?? entries[0])?.[1]
}

export function Hero() {
  const src = pickHero(heroModules)
  if (src) {
    return (
      <img
        src={src}
        alt="a younger person and an older person together"
        className="h-auto max-h-52 w-full object-contain"
      />
    )
  }
  return <HeroDrawing />
}

function HeroDrawing() {
  return (
    <svg
      viewBox="0 0 340 250"
      className="h-auto max-h-44 w-full max-w-[280px] text-ink"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="a younger person and an older person together"
    >
      <path d="M48 214h244" />
      <path d="M92 78c6-28 48-30 54 2" />
      <circle cx="118" cy="78" r="26" fill="var(--paper)" />
      <circle cx="108" cy="78" r="1.7" fill="currentColor" stroke="none" />
      <circle cx="128" cy="78" r="1.7" fill="currentColor" stroke="none" />
      <path d="M109 90c6 6 14 6 20 0" />
      <path d="M118 104v42" />
      <path d="M118 116 78 150" />
      <path d="M118 120 168 146" />
      <path d="M118 146 92 214" />
      <path d="M118 146 142 214" />

      <path d="M196 70c8-30 54-32 60 4" />
      <circle cx="226" cy="72" r="28" fill="var(--paper)" />
      <circle cx="216" cy="72" r="1.7" fill="currentColor" stroke="none" />
      <circle cx="236" cy="72" r="1.7" fill="currentColor" stroke="none" />
      <path d="M216 84c7 6 16 6 22 0" />
      <path d="M226 100v46" />
      <path d="M226 116 168 148" />
      <path d="M226 114 270 152" />
      <path d="M226 146 200 214" />
      <path d="M226 146 254 214" />
      <circle cx="168" cy="148" r="5" fill="var(--paper)" />
    </svg>
  )
}
