import { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  asChild?: boolean
}

export default function Button({
  children,
  variant = 'default',
  size = 'default',
  asChild = false,
  className: extraClassName = '',
  ...props
}: ButtonProps) {
  const baseClasses =
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep focus-visible:ring-offset-2 focus-visible:ring-offset-ground disabled:opacity-50 disabled:pointer-events-none'
  const variantClasses = {
    default: 'bg-pine text-[#f4f1e9] hover:bg-pine-deep',
    destructive: 'border border-lacre bg-panel text-lacre hover:bg-lacre-wash',
    outline: 'border border-linen-300 bg-panel text-ink hover:bg-linen-50',
    secondary: 'bg-linen-100 text-ink hover:bg-linen-200',
    ghost: 'text-ink-soft hover:bg-linen-100 hover:text-ink',
    link: 'text-pine underline-offset-4 hover:underline',
  }
  const sizeClasses = {
    default: 'h-10 px-4 py-2',
    sm: 'h-9 px-3',
    lg: 'h-11 px-6',
    icon: 'h-10 w-10',
  }

  const className = `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${extraClassName}`

  if (asChild) {
    return <>{children}</>
  }

  return (
    <button className={className} {...props}>
      {children}
    </button>
  )
}
