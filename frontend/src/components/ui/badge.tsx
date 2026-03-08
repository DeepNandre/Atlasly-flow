import * as React from 'react'
import { cn } from '@/lib/utils'

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  colorClass?: string
}

function Badge({ className, colorClass, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        colorClass ?? 'bg-atlasly-line text-atlasly-ink',
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}

export { Badge }
