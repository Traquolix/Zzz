export type AdminUser = {
  id: string
  username: string
  email: string
  role: string
  isActive: boolean
  organizationId: string | null
  organizationName: string | null
  allowedWidgets: string[]
  allowedLayers: string[]
}

export type CreateUserRequest = {
  username: string
  password: string
  email?: string
  role?: string
  organizationId?: string
}

export type UpdateUserRequest = {
  role?: string
  email?: string
  isActive?: boolean
  allowedWidgets?: string[]
  allowedLayers?: string[]
}

export type AdminOrganization = {
  id: string
  name: string
  slug: string
  isActive: boolean
  createdAt?: string
  allowedWidgets: string[]
  allowedLayers: string[]
  fiberAssignments: FiberAssignment[]
}

export type OrgSettings = {
  timezone: string
  speedAlertThreshold: number
  incidentAutoResolveMinutes: number
  shmEnabled: boolean
  allowedWidgets: string[]
  allowedLayers: string[]
}

export type FiberAssignment = {
  id: string
  fiberId: string
  assignedAt: string
}

export type AdminInfrastructure = {
  id: string
  name: string
  type: string
  fiberId: string
  startChannel: number
  endChannel: number
  organizationId: string
}

export type CreateInfrastructureRequest = {
  id: string
  name: string
  type: string
  fiberId: string
  startChannel: number
  endChannel: number
  organizationId?: string
}

export type AdminAlertRule = {
  id: string
  name: string
  ruleType: string
  threshold: number | null
  isActive: boolean
  dispatchChannel: string
  organizationId: string
}

export type CreateAlertRuleRequest = {
  name: string
  ruleType: string
  threshold?: number
  dispatchChannel?: string
  organizationId?: string
  isActive?: boolean
}

export type AlertLogEntry = {
  id: string
  ruleName: string
  fiberId: string
  channel: number
  detail: string
  dispatchedAt: string
}
