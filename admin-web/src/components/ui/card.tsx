import { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

export default function Card({ children, className = '', ...props }: CardProps) {
  return (
    <div className={`rounded-lg border border-linen-200 bg-panel text-card-foreground ${className}`} {...props}>
      {children}
    </div>
  )
}
