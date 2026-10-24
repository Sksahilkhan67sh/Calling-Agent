import type { ButtonHTMLAttributes } from 'react'

const variants = {
  primary: 'bg-primary text-primary-fg hover:opacity-90',
  secondary: 'border border-border hover:bg-card',
  danger: 'bg-danger text-bg hover:opacity-90',
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants
}

export function Button({ variant = 'primary', className = '', type = 'button', ...rest }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...rest}
    />
  )
}

// Same look for links that act as buttons, so styling stays in one place.
export const buttonClass = (variant: keyof typeof variants = 'primary') =>
  `inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium ${variants[variant]}`
