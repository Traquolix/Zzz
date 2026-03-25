export type APIKeyInfo = {
  id: string
  name: string
  prefix: string
  scopes: string[]
  requestCount: number
  createdAt: string
  lastUsedAt: string | null
  expiresAt: string | null
}

export type CreateAPIKeyResponse = {
  id: string
  name: string
  prefix: string
  key: string
}
