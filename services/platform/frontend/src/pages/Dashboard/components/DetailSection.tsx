export function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-[var(--dash-border)] pt-3">
      <h3 className="text-cq-xs font-medium text-[var(--dash-text-muted)] uppercase tracking-wider mb-3">{title}</h3>
      {children}
    </div>
  )
}
