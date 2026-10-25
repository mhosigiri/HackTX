import { BackLink, ScreenBody, YellowButton } from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'

/**
 * Dates, family availability, and the family timeline have no list endpoints
 * in the generated API. These routes keep the home tiles navigable.
 */
export function Soon({ title }: { title: string }) {
  useScreenTitle(title)
  return (
    <ScreenBody screen="soon">
      <BackLink to="/" />
      <h1 className="mt-8 font-hand text-5xl leading-none font-bold">{title}</h1>
      <p className="mt-4 max-w-[16rem] font-hand text-[1.8rem] leading-tight font-semibold text-muted">
        this shelf is next.
      </p>
      <div className="mt-auto pt-8">
        <YellowButton to="/">home →</YellowButton>
      </div>
    </ScreenBody>
  )
}
