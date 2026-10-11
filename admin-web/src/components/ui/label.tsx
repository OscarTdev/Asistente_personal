import { ReactNode } from 'react'

interface LabelProps {
  children: ReactNode
  className?: string
}

export default function Label({ children, className = '' }: LabelProps) {
  return (
    <label className={`text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-50 ${className}`}>
      {children}
    </label>
  )
}