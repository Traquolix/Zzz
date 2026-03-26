export function StatusBadge({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="text-cq-2xs font-medium px-1.5 py-0.5 rounded capitalize shrink-0"
      style={{ backgroundColor: `${color}20`, color }}
    >
      {label}
    </span>
  )
}
