import { useId, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { LANGUAGES, type LanguageId } from '@/lib/language'

const controlClass =
  'h-12 w-full rounded-2xl border-2 border-ink bg-paper px-4 font-sans text-base text-ink outline-none focus-visible:ring-2 focus-visible:ring-sun'

export function TextField({
  label,
  value,
  onChange,
  type = 'text',
  autoComplete,
  name,
  inputMode,
  readOnly,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: 'text' | 'email'
  autoComplete?: string
  name?: string
  inputMode?: 'text' | 'email'
  readOnly?: boolean
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="font-hand text-[1.85rem] leading-none font-semibold">
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        value={value}
        readOnly={readOnly}
        inputMode={inputMode}
        autoComplete={autoComplete}
        autoCapitalize={type === 'email' ? 'none' : 'words'}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
        className={`${controlClass} ${readOnly ? 'opacity-70' : ''}`}
      />
    </div>
  )
}

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  name,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  autoComplete?: string
  name?: string
}) {
  const id = useId()
  const [show, setShow] = useState(false)
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="font-hand text-[1.85rem] leading-none font-semibold">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          name={name}
          type={show ? 'text' : 'password'}
          value={value}
          autoComplete={autoComplete}
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          className={`${controlClass} pr-14`}
        />
        <button
          type="button"
          aria-label={show ? 'Hide password' : 'Show password'}
          onClick={() => setShow((open) => !open)}
          className="absolute top-1/2 right-2 grid size-10 -translate-y-1/2 place-items-center rounded-full"
        >
          {show ? <EyeOff className="size-5" /> : <Eye className="size-5" />}
        </button>
      </div>
    </div>
  )
}

export function AgeSlider({ value, onChange }: { value: number; onChange: (age: number) => void }) {
  const id = useId()
  return (
    <div className="flex flex-col gap-3">
      <label htmlFor={id} className="font-hand text-[1.85rem] leading-none font-semibold">
        age {value}
      </label>
      <input
        id={id}
        className="age-slider"
        type="range"
        min={1}
        max={120}
        step={1}
        value={value}
        aria-valuemin={1}
        aria-valuemax={120}
        aria-valuenow={value}
        aria-valuetext={`${value} years`}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  )
}

export function LanguageSelect({
  value,
  onChange,
}: {
  value: LanguageId
  onChange: (id: LanguageId) => void
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="font-hand text-[1.85rem] leading-none font-semibold">
        language
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value as LanguageId)}
          className={`${controlClass} appearance-none pr-12 font-hand text-[1.7rem] font-semibold`}
        >
          {LANGUAGES.map((language) => (
            <option key={language.id} value={language.id}>
              {language.label}
            </option>
          ))}
        </select>
        <span aria-hidden className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 font-hand text-3xl">
          ▾
        </span>
      </div>
    </div>
  )
}
