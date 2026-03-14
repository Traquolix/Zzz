import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { fetchAPIKeys, createAPIKey, revokeAPIKey, rotateAPIKey } from '@/api/apiKeys'
import type { CreateAPIKeyResponse } from '@/types/admin'

export function APIKeysPanel({ showCreate, onCloseCreate }: { showCreate: boolean; onCloseCreate: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyExpiry, setNewKeyExpiry] = useState('')
  const [revealedKey, setRevealedKey] = useState<CreateAPIKeyResponse | null>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  const { data: keys = [], isLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: fetchAPIKeys,
    refetchInterval: 30_000,
  })

  const createMutation = useMutation({
    mutationFn: ({ name, expiresAt }: { name: string; expiresAt?: string }) => createAPIKey(name, expiresAt),
    onSuccess: data => {
      setRevealedKey(data)
      onCloseCreate()
      setNewKeyName('')
      setNewKeyExpiry('')
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success(t('apiKeys.keyCreated'))
    },
  })

  const revokeMutation = useMutation({
    mutationFn: revokeAPIKey,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success(t('apiKeys.keyRevoked'))
    },
  })

  const rotateMutation = useMutation({
    mutationFn: rotateAPIKey,
    onSuccess: data => {
      setRevealedKey(data)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success(t('apiKeys.keyRotated'))
    },
  })

  const handleCreate = useCallback(() => {
    if (!newKeyName.trim()) return
    const expiresAt = newKeyExpiry ? new Date(newKeyExpiry).toISOString() : undefined
    createMutation.mutate({ name: newKeyName.trim(), expiresAt })
  }, [newKeyName, newKeyExpiry, createMutation])

  const handleRevoke = useCallback(
    (keyId: string) => {
      if (!confirm(t('apiKeys.revokeConfirm'))) return
      revokeMutation.mutate(keyId)
    },
    [revokeMutation, t],
  )

  const handleRotate = useCallback(
    (keyId: string) => {
      if (!confirm(t('apiKeys.rotateConfirm'))) return
      rotateMutation.mutate(keyId)
    },
    [rotateMutation, t],
  )

  const copyToClipboard = useCallback(
    (text: string) => {
      navigator.clipboard.writeText(text)
      toast.success(t('apiKeys.copied'))
    },
    [t],
  )

  // Click-outside to close create popover
  useEffect(() => {
    if (!showCreate) return
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onCloseCreate()
        setNewKeyName('')
        setNewKeyExpiry('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showCreate, onCloseCreate])

  // Reset form when popover closes
  useEffect(() => {
    if (!showCreate) {
      setNewKeyName('')
      setNewKeyExpiry('')
    }
  }, [showCreate])

  return (
    <div className="flex flex-col gap-2">
      {/* Create popover — anchored below the header */}
      {showCreate && (
        <div
          ref={popoverRef}
          className="flex flex-col gap-2 p-3 rounded-lg border border-[var(--proto-border)] bg-[var(--proto-surface-raised)]"
        >
          <input
            autoFocus
            type="text"
            value={newKeyName}
            onChange={e => setNewKeyName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') handleCreate()
              if (e.key === 'Escape') {
                onCloseCreate()
              }
            }}
            placeholder={t('apiKeys.namePlaceholder')}
            className="w-full px-2 py-1.5 rounded bg-[var(--proto-base)] border border-[var(--proto-border)] text-[length:var(--text-xs)] text-[var(--proto-text)] placeholder:text-[var(--proto-text-muted)] outline-none focus:border-[var(--proto-text-muted)]"
          />
          <div className="flex items-center gap-1.5">
            <label className="text-[length:var(--text-xxs)] text-[var(--proto-text-muted)] shrink-0">
              {t('apiKeys.expiresIn')}
            </label>
            <input
              type="date"
              value={newKeyExpiry}
              onChange={e => setNewKeyExpiry(e.target.value)}
              className="flex-1 px-1.5 py-1 rounded bg-[var(--proto-base)] border border-[var(--proto-border)] text-[length:var(--text-xxs)] text-[var(--proto-text)] outline-none focus:border-[var(--proto-text-muted)]"
            />
          </div>
          <button
            onClick={handleCreate}
            disabled={!newKeyName.trim() || createMutation.isPending}
            className="self-start px-3 py-1.5 rounded text-[length:var(--text-xs)] font-medium bg-[var(--proto-accent)] text-white disabled:opacity-30 cursor-pointer hover:brightness-110 transition-all"
          >
            {t('admin.create')}
          </button>
        </div>
      )}

      {/* Key revealed banner */}
      {revealedKey && (
        <div className="flex flex-col gap-1.5 p-2.5 rounded-md border border-amber-500/20 bg-amber-950/20">
          <p className="text-[length:var(--text-xs)] text-amber-300/80 leading-snug">{t('apiKeys.copyWarning')}</p>
          <div className="flex items-center gap-1.5">
            <code className="flex-1 px-1.5 py-1 rounded bg-[var(--proto-base)] text-[length:var(--text-xs)] text-[var(--proto-text)] font-mono break-all select-all leading-tight">
              {revealedKey.key}
            </code>
            <button
              onClick={() => copyToClipboard(revealedKey.key)}
              className="shrink-0 px-2.5 py-1 rounded text-[length:var(--text-xs)] bg-[var(--proto-surface-raised)] text-[var(--proto-text)] hover:bg-[var(--proto-border)] transition-colors cursor-pointer"
            >
              {t('apiKeys.copy')}
            </button>
          </div>
          <button
            onClick={() => setRevealedKey(null)}
            className="self-end text-[length:var(--text-xs)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] transition-colors cursor-pointer"
          >
            {t('apiKeys.close')}
          </button>
        </div>
      )}

      {/* Key list */}
      {isLoading ? (
        <div className="flex flex-col gap-1">
          {[1, 2].map(i => (
            <div key={i} className="h-8 rounded bg-[var(--proto-base)] animate-pulse" />
          ))}
        </div>
      ) : keys.length === 0 ? (
        <p className="text-[length:var(--text-xs)] text-[var(--proto-text-muted)]/60 py-2">
          {t('apiKeys.noKeysDescription')}
        </p>
      ) : (
        <div className="flex flex-col">
          {keys.map(key => {
            const isExpired = key.expiresAt && new Date(key.expiresAt) < new Date()
            return (
              <KeyRow
                key={key.id}
                name={key.name}
                prefix={key.prefix}
                isExpired={!!isExpired}
                lastUsed={key.lastUsedAt}
                requestCount={key.requestCount}
                onRotate={() => handleRotate(key.id)}
                onRevoke={() => handleRevoke(key.id)}
                rotating={rotateMutation.isPending && rotateMutation.variables === key.id}
                revoking={revokeMutation.isPending && revokeMutation.variables === key.id}
                t={t}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Key row ────────────────────────────────────────────────────

function KeyRow({
  name,
  prefix,
  isExpired,
  lastUsed,
  requestCount,
  onRotate,
  onRevoke,
  rotating,
  revoking,
  t,
}: {
  name: string
  prefix: string
  isExpired: boolean
  lastUsed: string | null
  requestCount: number
  onRotate: () => void
  onRevoke: () => void
  rotating: boolean
  revoking: boolean
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  return (
    <div className="group/row flex items-center gap-2.5 py-2 border-b border-[var(--proto-border)]/50 last:border-0">
      {/* Name + prefix */}
      <div className="flex items-center gap-1.5 min-w-0">
        <span
          className={`text-[length:var(--text-xs)] font-medium truncate ${
            isExpired ? 'text-[var(--proto-text-muted)] line-through' : 'text-[var(--proto-text)]'
          }`}
        >
          {name}
        </span>
        <code className="text-[length:var(--text-xxs)] text-[var(--proto-text-muted)]/60 font-mono shrink-0">
          {prefix}...
        </code>
        {isExpired && (
          <span className="text-[length:var(--text-xxs)] text-[var(--proto-red)]/70 shrink-0">
            {t('apiKeys.expired')}
          </span>
        )}
      </div>

      {/* Stats — visible on hover, always visible when sidebar is wide */}
      <span className="datahub-key-stats hidden group-hover/row:inline text-[length:var(--text-xxs)] text-[var(--proto-text-muted)]/50 tabular-nums shrink-0">
        {lastUsed ? formatRelative(lastUsed) : t('apiKeys.neverUsed')}
      </span>
      <span className="datahub-key-stats hidden group-hover/row:inline text-[length:var(--text-xxs)] text-[var(--proto-text-muted)]/50 tabular-nums shrink-0">
        {t('apiKeys.requestCount', { count: requestCount })}
      </span>

      <span className="flex-1" />

      {/* Inline actions — appear on hover */}
      <div className="flex items-center gap-1 opacity-0 group-hover/row:opacity-100 transition-opacity">
        <button
          onClick={onRotate}
          disabled={rotating}
          className="text-[length:var(--text-xxs)] text-[var(--proto-text-muted)] hover:text-[var(--proto-text-secondary)] transition-colors cursor-pointer px-1 py-0.5"
        >
          {t('apiKeys.rotate')}
        </button>
        <button
          onClick={onRevoke}
          disabled={revoking}
          className="text-[length:var(--text-xxs)] text-[var(--proto-red)]/70 hover:text-[var(--proto-red)] transition-colors cursor-pointer px-1 py-0.5"
        >
          {t('apiKeys.revoke')}
        </button>
      </div>
    </div>
  )
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  const days = Math.floor(hrs / 24)
  return `${days}d`
}

// ── Icons ──────────────────────────────────────────────────────────
