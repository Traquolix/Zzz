export function PanelEmptyState({ message, loading }: { message: string; loading?: boolean }) {
  return (
    <div className="flex items-center justify-center h-32 text-[var(--dash-text-muted)] text-cq-sm">
      {loading ? <span className="animate-pulse">{message}</span> : message}
    </div>
  )
}
