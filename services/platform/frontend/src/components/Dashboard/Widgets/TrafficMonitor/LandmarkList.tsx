import { useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { getSpeedBgClass } from '@/lib/speedColors'
import type { LandmarkInfo, LandmarkData, DataPoint, FiberGroup, DirectionGroup } from './types'
import { TIME_WINDOW_MS } from './types'
import { groupDetectionsIntoVehiclePasses } from '@/lib/groupDetections'
import { useTrafficMonitorActions } from './TrafficMonitorContext'
import type { FiberLine } from '@/types/fiber'

type LandmarkListProps = {
    landmarks: LandmarkInfo[]
    fibers: FiberLine[]
    landmarkData: Map<string, LandmarkData>
    selectedKey: string | null
    now: number
}

export function LandmarkList({
    landmarks,
    fibers,
    landmarkData,
    selectedKey,
    now,
}: LandmarkListProps) {
    const { t } = useTranslation()
    const { onSelect, onFlyTo, onRename, onToggleFavorite, onDelete } = useTrafficMonitorActions()
    const [editingKey, setEditingKey] = useState<string | null>(null)
    const [editingName, setEditingName] = useState('')
    const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null)
    // Track which folders are expanded (empty = all collapsed by default)
    const [expandedFibers, setExpandedFibers] = useState<Set<string>>(new Set())
    const [expandedDirections, setExpandedDirections] = useState<Set<string>>(new Set())

    const getStats = useCallback((points: DataPoint[]) => {
        const cutoff = now - TIME_WINDOW_MS
        const timeFiltered = points.filter(p => p.timestamp > cutoff)
        const grouped = groupDetectionsIntoVehiclePasses(timeFiltered)

        if (grouped.length === 0) {
            return { avg: 0, count: 0 }
        }

        const speeds = grouped.map(p => p.speed)
        return {
            avg: Math.round(speeds.reduce((a, b) => a + b, 0) / speeds.length),
            count: grouped.length
        }
    }, [now])

    // Group landmarks by parent fiber, then by direction, with favorites at the top
    const groupedLandmarks = useMemo(() => {
        const favorites = landmarks.filter(l => l.favorite)
        const regular = landmarks.filter(l => !l.favorite)

        // Build a map of parentFiberId -> fiber info
        const fiberMap = new Map<string, FiberLine>()
        fibers.forEach(f => fiberMap.set(f.id, f))

        // Get parent fiber ID from directional fiber ID
        const getParentFiberId = (fiberId: string): string => {
            const fiber = fiberMap.get(fiberId)
            return fiber?.parentFiberId || fiberId.replace(/:[01]$/, '')
        }

        const getDirection = (fiberId: string): 0 | 1 => {
            const fiber = fiberMap.get(fiberId)
            return fiber?.direction ?? (fiberId.endsWith(':1') ? 1 : 0)
        }

        const getFiberName = (fiberId: string): string => {
            const fiber = fiberMap.get(fiberId)
            if (fiber) return fiber.name.replace(/ \(Direction [01]\)$/, '')
            return fiberId.replace(/:[01]$/, '')
        }

        const groups: FiberGroup<LandmarkInfo>[] = []

        // Add favorites group if any exist
        if (favorites.length > 0) {
            // Group favorites by parent fiber and direction
            const favByParent = new Map<string, Map<number, LandmarkInfo[]>>()
            favorites.forEach(l => {
                const parent = getParentFiberId(l.fiberId)
                const dir = getDirection(l.fiberId)
                if (!favByParent.has(parent)) favByParent.set(parent, new Map())
                const dirMap = favByParent.get(parent)!
                if (!dirMap.has(dir)) dirMap.set(dir, [])
                dirMap.get(dir)!.push(l)
            })

            const favDirections: DirectionGroup<LandmarkInfo>[] = []
            favByParent.forEach((dirMap, _parent) => {
                dirMap.forEach((items, dir) => {
                    const fiberId = items[0]?.fiberId || ''
                    favDirections.push({
                        direction: dir as 0 | 1,
                        fiberId,
                        items: items.sort((a, b) => a.name.localeCompare(b.name))
                    })
                })
            })

            if (favDirections.length > 0) {
                groups.push({
                    parentFiberId: '__favorites__',
                    fiberName: t('traffic.landmarks.favorites'),
                    directions: favDirections.sort((a, b) => a.direction - b.direction)
                })
            }
        }

        // Group regular landmarks by parent fiber, then direction
        const parentGroups = new Map<string, Map<number, LandmarkInfo[]>>()
        regular.forEach(l => {
            const parent = getParentFiberId(l.fiberId)
            const dir = getDirection(l.fiberId)
            if (!parentGroups.has(parent)) parentGroups.set(parent, new Map())
            const dirMap = parentGroups.get(parent)!
            if (!dirMap.has(dir)) dirMap.set(dir, [])
            dirMap.get(dir)!.push(l)
        })

        // Convert to FiberGroup array
        const sortedParents = Array.from(parentGroups.keys()).sort()
        for (const parentId of sortedParents) {
            const dirMap = parentGroups.get(parentId)!
            const directions: DirectionGroup<LandmarkInfo>[] = []

            // Sort by direction (0 first, then 1)
            const sortedDirs = Array.from(dirMap.keys()).sort()
            for (const dir of sortedDirs) {
                const items = dirMap.get(dir)!
                const fiberId = items[0]?.fiberId || `${parentId}:${dir}`
                directions.push({
                    direction: dir as 0 | 1,
                    fiberId,
                    items: items.sort((a, b) => a.channel - b.channel)
                })
            }

            // Get display name from first landmark's fiber
            const firstFiberId = directions[0]?.items[0]?.fiberId
            const fiberName = firstFiberId ? getFiberName(firstFiberId) : parentId

            groups.push({
                parentFiberId: parentId,
                fiberName,
                directions
            })
        }

        return groups
    }, [landmarks, fibers, t])

    const toggleFiberExpand = useCallback((parentFiberId: string) => {
        setExpandedFibers(prev => {
            const next = new Set(prev)
            if (next.has(parentFiberId)) {
                next.delete(parentFiberId)
            } else {
                next.add(parentFiberId)
            }
            return next
        })
    }, [])

    const toggleDirectionExpand = useCallback((dirKey: string) => {
        setExpandedDirections(prev => {
            const next = new Set(prev)
            if (next.has(dirKey)) {
                next.delete(dirKey)
            } else {
                next.add(dirKey)
            }
            return next
        })
    }, [])

    const startEditing = useCallback((key: string, currentName: string, e: React.MouseEvent) => {
        e.stopPropagation()
        setEditingKey(key)
        setEditingName(currentName)
    }, [])

    const saveName = useCallback((landmark: LandmarkInfo) => {
        onRename(landmark.fiberId, landmark.channel, editingName)
        setEditingKey(null)
    }, [onRename, editingName])

    const handleDelete = useCallback((landmark: LandmarkInfo, e: React.MouseEvent) => {
        e.stopPropagation()
        if (confirmDeleteKey === landmark.key) {
            onDelete(landmark.fiberId, landmark.channel)
            setConfirmDeleteKey(null)
        } else {
            setConfirmDeleteKey(landmark.key)
        }
    }, [confirmDeleteKey, onDelete])

    const handleToggleFavorite = useCallback((landmark: LandmarkInfo, e: React.MouseEvent) => {
        e.stopPropagation()
        onToggleFavorite(landmark.fiberId, landmark.channel)
    }, [onToggleFavorite])

    if (landmarks.length === 0) return null

    return (
        <div className="flex-shrink-0 max-h-48 overflow-y-auto border-b border-slate-100 -mt-px">
            {groupedLandmarks.map((group) => {
                const isFiberExpanded = expandedFibers.has(group.parentFiberId)
                const isFavoritesGroup = group.parentFiberId === '__favorites__'
                const totalItems = group.directions.reduce((sum, d) => sum + d.items.length, 0)

                return (
                    <div key={group.parentFiberId}>
                        {/* Parent Fiber header */}
                        <button
                            onClick={() => toggleFiberExpand(group.parentFiberId)}
                            className="w-full px-3 py-1.5 flex items-center gap-2 bg-slate-100 hover:bg-slate-200 transition-colors border-b border-slate-200 sticky top-0 z-20"
                        >
                            <svg
                                className={`w-3 h-3 text-slate-500 transition-transform ${isFiberExpanded ? 'rotate-90' : ''}`}
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                            {isFavoritesGroup && (
                                <svg className="w-3 h-3 text-amber-500" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                                </svg>
                            )}
                            <span className="text-xs font-semibold text-slate-700 truncate flex-1 text-left">
                                {group.fiberName}
                            </span>
                            <span className="text-[10px] text-slate-500">
                                {totalItems}
                            </span>
                        </button>

                        {/* Direction subgroups */}
                        {isFiberExpanded && group.directions.map((dirGroup) => {
                            const dirKey = `${group.parentFiberId}:${dirGroup.direction}`
                            const isDirExpanded = expandedDirections.has(dirKey)

                            return (
                                <div key={dirKey}>
                                    {/* Direction header - only show if parent has multiple directions */}
                                    {group.directions.length > 1 && (
                                        <button
                                            onClick={() => toggleDirectionExpand(dirKey)}
                                            className="w-full pl-6 pr-3 py-1 flex items-center gap-2 bg-slate-50 hover:bg-slate-100 transition-colors border-b border-slate-100 sticky top-[26px] z-10"
                                        >
                                            <svg
                                                className={`w-2.5 h-2.5 text-slate-400 transition-transform ${isDirExpanded ? 'rotate-90' : ''}`}
                                                fill="none"
                                                viewBox="0 0 24 24"
                                                stroke="currentColor"
                                            >
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                            </svg>
                                            <span className="text-[11px] text-slate-500">
                                                {dirGroup.direction === 0 ? t('traffic.landmarks.directionForward') : t('traffic.landmarks.directionBackward')}
                                            </span>
                                            <span className="text-[10px] text-slate-400 ml-auto">
                                                {dirGroup.items.length}
                                            </span>
                                        </button>
                                    )}

                                    {/* Landmarks in direction */}
                                    {(group.directions.length === 1 || isDirExpanded) && dirGroup.items.map((landmark) => {
                                        const data = landmarkData.get(landmark.key)
                                        const stats = data ? getStats(data.points) : { avg: 0, count: 0 }
                                        const isSelected = selectedKey === landmark.key
                                        const isEditing = editingKey === landmark.key
                                        const isConfirmingDelete = confirmDeleteKey === landmark.key

                                        return (
                                            <div
                                                key={landmark.key}
                                                onClick={() => !isEditing && onSelect(landmark)}
                                                className={`group w-full px-3 py-2 flex items-center justify-between text-left transition-colors cursor-pointer ${
                                                    isSelected
                                                        ? 'bg-blue-50 border-l-2 border-blue-500'
                                                        : 'hover:bg-slate-50 border-l-2 border-transparent'
                                                } ${group.directions.length > 1 ? 'pl-8' : 'pl-6'}`}
                                            >
                                                <div className="min-w-0 flex-1">
                                                    {isEditing ? (
                                                        <input
                                                            type="text"
                                                            value={editingName}
                                                            onChange={(e) => setEditingName(e.target.value)}
                                                            onKeyDown={(e) => {
                                                                if (e.key === 'Enter') saveName(landmark)
                                                                if (e.key === 'Escape') setEditingKey(null)
                                                            }}
                                                            onBlur={() => saveName(landmark)}
                                                            onClick={(e) => e.stopPropagation()}
                                                            autoFocus
                                                            className="w-full border border-slate-300 rounded px-1.5 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                        />
                                                    ) : (
                                                        <>
                                                            <div
                                                                className={`text-sm font-medium truncate ${isSelected ? 'text-blue-700 cursor-text' : 'text-slate-700'}`}
                                                                onClick={(e) => {
                                                                    if (isSelected) {
                                                                        e.stopPropagation()
                                                                        startEditing(landmark.key, landmark.name, e)
                                                                    }
                                                                }}
                                                            >
                                                                {landmark.name}
                                                            </div>
                                                            <div className="text-[10px] text-slate-400">
                                                                Ch. {landmark.channel}
                                                            </div>
                                                        </>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
                                                    <div className={`flex items-center gap-0.5 ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}>
                                                        {/* Favorite button */}
                                                        <button
                                                            onClick={(e) => handleToggleFavorite(landmark, e)}
                                                            className={`p-1 transition-colors ${
                                                                landmark.favorite
                                                                    ? 'text-amber-500 hover:text-amber-600'
                                                                    : 'text-slate-300 hover:text-amber-500'
                                                            }`}
                                                            title={landmark.favorite ? t('traffic.landmarks.removeFromFavorites') : t('traffic.landmarks.addToFavorites')}
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill={landmark.favorite ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                                                            </svg>
                                                        </button>
                                                        {/* Fly to button */}
                                                        <button
                                                            onClick={(e) => onFlyTo(landmark, e)}
                                                            className="p-1 text-slate-400 hover:text-blue-500 transition-colors"
                                                            title={t('traffic.landmarks.goToLocation')}
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                                            </svg>
                                                        </button>
                                                        {/* Delete button */}
                                                        <button
                                                            onClick={(e) => handleDelete(landmark, e)}
                                                            onBlur={() => setConfirmDeleteKey(null)}
                                                            className={`p-1 transition-colors ${
                                                                isConfirmingDelete
                                                                    ? 'text-white bg-red-500 rounded'
                                                                    : 'text-slate-400 hover:text-red-500'
                                                            }`}
                                                            title={isConfirmingDelete ? t('common.clickToConfirm') : t('common.delete')}
                                                        >
                                                            {isConfirmingDelete ? (
                                                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                                                </svg>
                                                            ) : (
                                                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                                </svg>
                                                            )}
                                                        </button>
                                                    </div>
                                                    <div className="text-right w-16">
                                                        <div className={`text-sm font-semibold ${stats.avg > 0 ? 'text-slate-700' : 'text-slate-300'}`}>
                                                            {stats.avg > 0 ? `${stats.avg}` : '—'}
                                                        </div>
                                                        <div className="text-[10px] text-slate-400">
                                                            {stats.count > 0 ? `${stats.count} ${t('traffic.landmarks.vehicleUnit')}` : ''}
                                                        </div>
                                                    </div>
                                                    {stats.count > 0 && (
                                                        <div className={`w-2 h-2 rounded-full ${getSpeedBgClass(stats.avg)}`} />
                                                    )}
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            )
                        })}
                    </div>
                )
            })}
        </div>
    )
}
