import { Hero } from '@/components/brand/Hero'
import { HandLink, InviteNote, ScreenBody, YellowButton } from '@/components/ui/chrome'
import { useScreenTitle } from '@/lib/useScreenTitle'

export function Welcome() {
  useScreenTitle('tell me more')
  return (
    <ScreenBody screen="welcome" className="items-center px-7 pt-6 pb-5 text-center">
      <h1 className="font-hand text-[3.15rem] leading-none font-bold">tell me more</h1>
      <div className="flex min-h-0 w-full flex-1 items-center justify-center py-2">
        <Hero />
      </div>
      <p className="font-hand text-[2.15rem] leading-[0.95] font-semibold">
        keep their stories
        <br />
        close.
      </p>
      <div className="mt-5 flex w-full flex-col items-center gap-3">
        <InviteNote />
        <YellowButton to="/sign-up">get started →</YellowButton>
        <HandLink to="/sign-in">sign in</HandLink>
      </div>
    </ScreenBody>
  )
}
