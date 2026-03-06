type SkeletonPatternType = 'line' | 'title' | 'paragraph' | 'card'

type SkeletonProps = {
  className?: string
  lines?: number
  pattern?: SkeletonPatternType
}

const widthPatterns: Record<SkeletonPatternType, number[]> = {
  line: [100],
  title: [100, 60],
  paragraph: [100, 95, 85, 70],
  card: [60, 100, 100, 90, 75],
}

const deterministicTaper = [100, 95, 85, 70, 60]

export function Skeleton({ className = '', lines = 1, pattern }: SkeletonProps) {
  const widths = pattern ? widthPatterns[pattern] : deterministicTaper.slice(0, Math.max(1, lines))

  return (
    <div className={`space-y-3 ${className}`}>
      {widths.map((width, i) => (
        <div
          key={i}
          className="h-4 bg-slate-200 dark:bg-slate-700 rounded animate-pulse"
          style={{ width: `${width}%` }}
        />
      ))}
    </div>
  )
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex gap-4">
          {Array.from({ length: cols }, (_, j) => (
            <div key={j} className="h-4 bg-slate-200 dark:bg-slate-700 rounded animate-pulse flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}
