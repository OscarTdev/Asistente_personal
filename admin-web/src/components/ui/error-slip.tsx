import * as React from 'react'
import { cn } from '../../lib/utils'

interface ErrorSlipProps {
  message: string | null
  className?: string
}

export function ErrorSlip({ message, className }: ErrorSlipProps) {
  if (!message) return null
  return (
    <div
      className={cn(
        'slip animate-slide-in',
        className
      )}
      role="alert"
    >
      {message}
    </div>
  )
}