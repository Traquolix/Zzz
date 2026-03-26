import { cn } from '@/lib/utils'

export function ColorDot({ color, className }: { color?: string; className?: string }) {
  return <span className={cn('shrink-0 w-2 h-2 rounded-full', className)} style={{ backgroundColor: color }} />
}
