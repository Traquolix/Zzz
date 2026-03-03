import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

type TooltipProps = {
    children: ReactNode
    content: string
    side?: 'top' | 'right' | 'bottom' | 'left'
    delayDuration?: number
    className?: string
}

export function TooltipProvider({ children }: { children: ReactNode }) {
    return (
        <TooltipPrimitive.Provider delayDuration={200}>
            {children}
        </TooltipPrimitive.Provider>
    )
}

export function Tooltip({ children, content, side = 'top', delayDuration, className }: TooltipProps) {
    return (
        <TooltipPrimitive.Root delayDuration={delayDuration}>
            <TooltipPrimitive.Trigger asChild>
                {children}
            </TooltipPrimitive.Trigger>
            <TooltipPrimitive.Portal>
                <TooltipPrimitive.Content
                    side={side}
                    sideOffset={4}
                    className={cn(
                        'z-[3000] rounded-md bg-slate-900 dark:bg-slate-100 px-3 py-1.5 text-xs text-slate-100 dark:text-slate-900 shadow-md',
                        'animate-in fade-in-0 slide-in-from-bottom-1 duration-150',
                        className
                    )}
                >
                    {content}
                    <TooltipPrimitive.Arrow className="fill-slate-900 dark:fill-slate-100" />
                </TooltipPrimitive.Content>
            </TooltipPrimitive.Portal>
        </TooltipPrimitive.Root>
    )
}
