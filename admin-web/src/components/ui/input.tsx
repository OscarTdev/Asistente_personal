import { InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  onChangeValue?: (value: string) => void
}

export default function Input({ onChangeValue, className = '', ...props }: InputProps) {
  const { value, ...rest } = props
  return (
    <input
      value={value}
      onChange={(e) => onChangeValue?.(e.target.value)}
      className={`
        flex h-11 w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm text-ink
        placeholder:text-linen-600
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep focus-visible:ring-offset-0
        focus-visible:border-brass-deep
        disabled:cursor-not-allowed disabled:opacity-50
        ${className}
      `}
      {...rest}
    />
  )
}
