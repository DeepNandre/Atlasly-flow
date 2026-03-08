import * as React from 'react'
import { cn } from '@/lib/utils'

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        'flex h-9 w-full rounded-md border border-atlasly-line bg-atlasly-paper px-3 py-1 text-sm text-atlasly-ink placeholder:text-atlasly-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-atlasly-teal disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export { Input }
