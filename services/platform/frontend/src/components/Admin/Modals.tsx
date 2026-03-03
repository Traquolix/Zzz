import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AVAILABLE_WIDGETS, AVAILABLE_LAYERS } from '@/constants/permissions'
import type { CreateUserRequest, CreateAlertRuleRequest, CreateInfrastructureRequest, UpdateUserRequest, AdminUser, AdminOrganization, AdminInfrastructure, AdminAlertRule } from '@/types/admin'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { CheckboxGrid } from './shared'
import { FormField } from '@/components/ui/form-field'

export function CreateUserModal({
    onSubmit,
    onClose,
}: {
    onSubmit: (data: CreateUserRequest) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [email, setEmail] = useState('')
    const [role, setRole] = useState('viewer')
    const [touched, setTouched] = useState<Record<string, boolean>>({})

    const handleBlur = (field: string) => {
        setTouched(prev => ({ ...prev, [field]: true }))
    }

    const validateEmail = (value: string): string | undefined => {
        if (!value) return undefined
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
        return emailRegex.test(value) ? undefined : 'Invalid email format'
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        onSubmit({ username, password, email, role })
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.createUser')}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('admin.username')}
                        type="text"
                        value={username}
                        onChange={e => setUsername(e.target.value)}
                        onBlur={() => handleBlur('username')}
                        required
                        touched={touched.username}
                        error={touched.username && !username ? 'Username is required' : undefined}
                    />
                    <FormField
                        label={t('admin.password')}
                        type="password"
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        onBlur={() => handleBlur('password')}
                        required
                        touched={touched.password}
                        error={touched.password && !password ? 'Password is required' : undefined}
                    />
                    <FormField
                        label={t('admin.email')}
                        type="email"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                        onBlur={() => handleBlur('email')}
                        touched={touched.email}
                        error={touched.email ? validateEmail(email) : undefined}
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.role')}</label>
                        <select value={role} onChange={e => setRole(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500">
                            <option value="viewer">Viewer</option>
                            <option value="operator">Operator</option>
                            <option value="admin">Admin</option>
                        </select>
                    </div>
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <button type="submit" disabled={!username || !password}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                            {t('admin.create')}
                        </button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function CreateOrgModal({
    onSubmit,
    onClose,
}: {
    onSubmit: (name: string) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [name, setName] = useState('')

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        onSubmit(name)
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.createOrg')}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('common.name')}
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        required
                    />
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <button type="submit" disabled={!name}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                            {t('admin.create')}
                        </button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function CreateRuleModal({
    onSubmit,
    onClose,
}: {
    onSubmit: (data: CreateAlertRuleRequest) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [name, setName] = useState('')
    const [ruleType, setRuleType] = useState('speed_below')
    const [threshold, setThreshold] = useState('')
    const [dispatch, setDispatch] = useState('log')

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        onSubmit({
            name,
            ruleType,
            threshold: threshold ? Number(threshold) : undefined,
            dispatchChannel: dispatch,
        })
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.createRule')}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('common.name')}
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        required
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.ruleType')}</label>
                        <select value={ruleType} onChange={e => setRuleType(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500">
                            <option value="speed_below">Speed Below</option>
                            <option value="incident_type">Incident Type</option>
                        </select>
                    </div>
                    <FormField
                        label={t('admin.threshold')}
                        type="number"
                        value={threshold}
                        onChange={e => setThreshold(e.target.value)}
                        placeholder="Optional"
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.dispatch')}</label>
                        <select value={dispatch} onChange={e => setDispatch(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500">
                            <option value="log">Log</option>
                            <option value="webhook">Webhook</option>
                            <option value="email">Email</option>
                        </select>
                    </div>
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <button type="submit" disabled={!name}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                            {t('admin.create')}
                        </button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function EditUserModal({
    user,
    onSubmit,
    onClose,
}: {
    user: AdminUser
    onSubmit: (userId: string, data: UpdateUserRequest) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [role, setRole] = useState(user.role)
    const [email, setEmail] = useState(user.email)
    const [isActive, setIsActive] = useState(user.isActive)
    const [allowedWidgets, setAllowedWidgets] = useState(user.allowedWidgets)
    const [allowedLayers, setAllowedLayers] = useState(user.allowedLayers)
    const [submitting, setSubmitting] = useState(false)
    const [touched, setTouched] = useState<Record<string, boolean>>({})

    const handleBlur = (field: string) => {
        setTouched(prev => ({ ...prev, [field]: true }))
    }

    const validateEmail = (value: string): string | undefined => {
        if (!value) return undefined
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
        return emailRegex.test(value) ? undefined : 'Invalid email format'
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            setSubmitting(true)
            onSubmit(user.id, {
                role,
                email,
                isActive,
                allowedWidgets,
                allowedLayers,
            })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-2xl">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.edit')} - {user.username}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('admin.email')}
                        type="email"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                        onBlur={() => handleBlur('email')}
                        touched={touched.email}
                        error={touched.email ? validateEmail(email) : undefined}
                    />

                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.role')}</label>
                        <select
                            value={role}
                            onChange={e => setRole(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500"
                        >
                            <option value="viewer">Viewer</option>
                            <option value="operator">Operator</option>
                            <option value="admin">Admin</option>
                        </select>
                    </div>

                    <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={isActive}
                            onChange={e => setIsActive(e.target.checked)}
                            className="rounded border-slate-300 dark:border-slate-600 text-blue-600 focus:ring-blue-500"
                        />
                        {t('admin.status')}
                    </label>

                    <CheckboxGrid
                        items={AVAILABLE_WIDGETS}
                        selected={allowedWidgets}
                        onChange={setAllowedWidgets}
                        label={t('admin.settings.widgets')}
                    />

                    <CheckboxGrid
                        items={AVAILABLE_LAYERS}
                        selected={allowedLayers}
                        onChange={setAllowedLayers}
                        label={t('admin.settings.layers')}
                    />

                    <div className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded p-3 text-xs text-slate-600 dark:text-slate-400">
                        {t('admin.settings.inheritNote')}
                    </div>

                    <div className="flex justify-end gap-3 pt-4">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <Button
                            type="submit"
                            isLoading={submitting}
                            loadingText={t('common.loading')}
                        >
                            {t('admin.save')}
                        </Button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function EditOrgModal({
    org,
    onSubmit,
    onClose,
}: {
    org: AdminOrganization
    onSubmit: (orgId: string, data: { name?: string; isActive?: boolean }) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [name, setName] = useState(org.name)
    const [isActive, setIsActive] = useState(org.isActive)
    const [submitting, setSubmitting] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            setSubmitting(true)
            onSubmit(org.id, { name, isActive })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.edit')} - {org.name}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('common.name')}
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        required
                    />
                    <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={isActive}
                            onChange={e => setIsActive(e.target.checked)}
                            className="rounded border-slate-300 dark:border-slate-600 text-blue-600 focus:ring-blue-500"
                        />
                        {t('admin.status')}
                    </label>
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <Button type="submit" isLoading={submitting} loadingText={t('common.loading')}>
                            {t('admin.save')}
                        </Button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function CreateInfraModal({
    onSubmit,
    onClose,
}: {
    onSubmit: (data: CreateInfrastructureRequest) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [id, setId] = useState('')
    const [name, setName] = useState('')
    const [type, setType] = useState('bridge')
    const [fiberId, setFiberId] = useState('')
    const [startChannel, setStartChannel] = useState('')
    const [endChannel, setEndChannel] = useState('')
    const [touched, setTouched] = useState<Record<string, boolean>>({})

    const handleBlur = (field: string) => {
        setTouched(prev => ({ ...prev, [field]: true }))
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        onSubmit({
            id,
            name,
            type,
            fiberId,
            startChannel: Number(startChannel),
            endChannel: Number(endChannel),
        })
    }

    const isValid = id && name && fiberId && startChannel && endChannel

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.createInfra')}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label="ID"
                        type="text"
                        value={id}
                        onChange={e => setId(e.target.value)}
                        onBlur={() => handleBlur('id')}
                        required
                        touched={touched.id}
                        error={touched.id && !id ? 'ID is required' : undefined}
                    />
                    <FormField
                        label={t('common.name')}
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        onBlur={() => handleBlur('name')}
                        required
                        touched={touched.name}
                        error={touched.name && !name ? 'Name is required' : undefined}
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.type')}</label>
                        <select value={type} onChange={e => setType(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500">
                            <option value="bridge">Bridge</option>
                            <option value="tunnel">Tunnel</option>
                            <option value="viaduct">Viaduct</option>
                            <option value="overpass">Overpass</option>
                        </select>
                    </div>
                    <FormField
                        label={t('common.fiber')}
                        type="text"
                        value={fiberId}
                        onChange={e => setFiberId(e.target.value)}
                        onBlur={() => handleBlur('fiberId')}
                        required
                        touched={touched.fiberId}
                        error={touched.fiberId && !fiberId ? 'Fiber ID is required' : undefined}
                    />
                    <div className="grid grid-cols-2 gap-3">
                        <FormField
                            label={t('admin.startChannel')}
                            type="number"
                            value={startChannel}
                            onChange={e => setStartChannel(e.target.value)}
                            onBlur={() => handleBlur('startChannel')}
                            required
                            touched={touched.startChannel}
                            error={touched.startChannel && !startChannel ? 'Required' : undefined}
                        />
                        <FormField
                            label={t('admin.endChannel')}
                            type="number"
                            value={endChannel}
                            onChange={e => setEndChannel(e.target.value)}
                            onBlur={() => handleBlur('endChannel')}
                            required
                            touched={touched.endChannel}
                            error={touched.endChannel && !endChannel ? 'Required' : undefined}
                        />
                    </div>
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <button type="submit" disabled={!isValid}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                            {t('admin.create')}
                        </button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function EditInfraModal({
    infra,
    onSubmit,
    onClose,
}: {
    infra: AdminInfrastructure
    onSubmit: (id: string, data: Partial<CreateInfrastructureRequest>) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [name, setName] = useState(infra.name)
    const [type, setType] = useState(infra.type)
    const [fiberId, setFiberId] = useState(infra.fiberId)
    const [startChannel, setStartChannel] = useState(String(infra.startChannel))
    const [endChannel, setEndChannel] = useState(String(infra.endChannel))
    const [submitting, setSubmitting] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            setSubmitting(true)
            onSubmit(infra.id, {
                name,
                type,
                fiberId,
                startChannel: Number(startChannel),
                endChannel: Number(endChannel),
            })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.edit')} - {infra.name}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('common.name')}
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        required
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.type')}</label>
                        <select value={type} onChange={e => setType(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500">
                            <option value="bridge">Bridge</option>
                            <option value="tunnel">Tunnel</option>
                            <option value="viaduct">Viaduct</option>
                            <option value="overpass">Overpass</option>
                        </select>
                    </div>
                    <FormField
                        label={t('common.fiber')}
                        type="text"
                        value={fiberId}
                        onChange={e => setFiberId(e.target.value)}
                        required
                    />
                    <div className="grid grid-cols-2 gap-3">
                        <FormField
                            label={t('admin.startChannel')}
                            type="number"
                            value={startChannel}
                            onChange={e => setStartChannel(e.target.value)}
                            required
                        />
                        <FormField
                            label={t('admin.endChannel')}
                            type="number"
                            value={endChannel}
                            onChange={e => setEndChannel(e.target.value)}
                            required
                        />
                    </div>
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <Button type="submit" isLoading={submitting} loadingText={t('common.loading')}>
                            {t('admin.save')}
                        </Button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}

export function EditRuleModal({
    rule,
    onSubmit,
    onClose,
}: {
    rule: AdminAlertRule
    onSubmit: (id: string, data: Partial<CreateAlertRuleRequest>) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    const [name, setName] = useState(rule.name)
    const [threshold, setThreshold] = useState(rule.threshold !== null ? String(rule.threshold) : '')
    const [dispatch, setDispatch] = useState(rule.dispatchChannel)
    const [isActive, setIsActive] = useState(rule.isActive)
    const [submitting, setSubmitting] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            setSubmitting(true)
            onSubmit(rule.id, {
                name,
                threshold: threshold ? Number(threshold) : undefined,
                dispatchChannel: dispatch,
                isActive,
            })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <Modal open={true} onClose={onClose} className="max-w-md">
            <div className="p-6">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('admin.edit')} - {rule.name}</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <FormField
                        label={t('common.name')}
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        required
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.ruleType')}</label>
                        <div className="px-3 py-2 text-sm bg-slate-100 dark:bg-slate-800 rounded-md text-slate-500 dark:text-slate-400">
                            {rule.ruleType}
                        </div>
                    </div>
                    <FormField
                        label={t('admin.threshold')}
                        type="number"
                        value={threshold}
                        onChange={e => setThreshold(e.target.value)}
                        placeholder="Optional"
                    />
                    <div className="space-y-1.5">
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{t('admin.dispatch')}</label>
                        <select value={dispatch} onChange={e => setDispatch(e.target.value)}
                            className="w-full rounded-md border px-3 py-2 text-sm transition-colors bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-ring border-input hover:border-slate-400 dark:hover:border-slate-500">
                            <option value="log">Log</option>
                            <option value="webhook">Webhook</option>
                            <option value="email">Email</option>
                        </select>
                    </div>
                    <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={isActive}
                            onChange={e => setIsActive(e.target.checked)}
                            className="rounded border-slate-300 dark:border-slate-600 text-blue-600 focus:ring-blue-500"
                        />
                        {t('admin.status')}
                    </label>
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                            {t('common.cancel')}
                        </button>
                        <Button type="submit" isLoading={submitting} loadingText={t('common.loading')}>
                            {t('admin.save')}
                        </Button>
                    </div>
                </form>
            </div>
        </Modal>
    )
}
