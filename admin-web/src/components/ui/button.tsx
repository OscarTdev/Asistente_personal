import { ReactNode } from 'react'

interface ButtonProps {
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
  ...props
}: ButtonProps) {
  // We'll create a simple button with Tailwind classes
  const baseClasses = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none'
  const variantClasses = {
    default: 'bg-primary text-primary-foreground hover:bg-primary/90',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
    outline: 'border border-input hover:bg-accent hover:text-accent-foreground',
    secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
    ghost: 'hover:bg-accent hover:text-accent-foreground',
    link: 'underline-offset-4 hover:underline text-primary',
  }
  const sizeClasses = {
    default: 'h-10 px-4 py-2',
    sm: 'h-9 px-3 rounded',
    lg: 'h-11 px-8',
    icon: 'h-10 w-10',
  }

  const ClassName = `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]}`

  if (asChild) {
    return <>{children}</>
  }

  return (
    <button className={ClassName} {...props}>
      {children}
    </button>
  )
}