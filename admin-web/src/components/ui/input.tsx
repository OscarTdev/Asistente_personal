import { ReactNode } from 'react'

interface InputProps {
  type?: string
  value?: string
  onChange?: (value: string) => void
  placeholder?: string
  className?: string
}

export default function Input({
  type = 'text',
  value = '',
  onChange,
  placeholder = '',
  className = '',
  ...props
}: InputProps) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`
        flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50
        ${className}
      `}
      {...props}
    />
  )
}