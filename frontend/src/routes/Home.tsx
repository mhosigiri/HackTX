import { Link } from 'react-router'
import {
  AvailabilityIcon,
  CaptureIcon,
  DatesIcon,
  MemoriesIcon,
  TimelineIcon,
  TreeIcon,
} from '@/components/ui/sketchIcons'
import { ScreenBody } from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'

const tiles = [
  { to: '/capture', label: 'capture\nan object', icon: CaptureIcon },
  { to: '/dates', label: 'important\ndates', icon: DatesIcon },
  { to: '/family', label: 'family\ntree', icon: TreeIcon },
  { to: '/stories', label: 'family\nmemories', icon: MemoriesIcon },
  { to: '/availability', label: 'family\navailability', icon: AvailabilityIcon },
  { to: '/timeline', label: 'timeline', icon: TimelineIcon },
]

/** Home hub from the page map. Dates, availability, and timeline have no API yet. */
export function Home() {
  useScreenTitle('tell me more')
  return (
    <ScreenBody screen="home" className="pb-6">
      <header className="flex items-center justify-between gap-3">
        <h1 className="font-hand text-[2.7rem] leading-none font-bold">tell me more</h1>
        <Link
          to="/account"
          aria-label="Account"
          className="grid size-12 shrink-0 place-items-center rounded-full border-2 border-ink"
        >
          <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <circle cx="12" cy="8" r="3.2" />
            <path d="M5.5 19.5c1.2-3.4 3.5-5 6.5-5s5.3 1.6 6.5 5" strokeLinecap="round" />
          </svg>
        </Link>
      </header>
      <nav className="mt-6 grid min-h-0 flex-1 grid-cols-2 grid-rows-3 gap-3" aria-label="Home">
        {tiles.map((tile) => {
          const Icon = tile.icon
          return (
            <Link
              key={tile.to}
              to={tile.to}
              className="flex min-h-28 flex-col items-center justify-center gap-2 rounded-[1.6rem] border-2 border-ink px-3 py-3 text-center transition-colors hover:bg-ink/5 active:bg-sun active:text-black"
            >
              <Icon />
              <span className="font-hand text-[1.65rem] leading-[0.9] font-semibold whitespace-pre-line">
                {tile.label}
              </span>
            </Link>
          )
        })}
      </nav>
    </ScreenBody>
  )
}
