import { useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { getSpeedBgClass } from '@/lib/speedColors'
import type { FiberSection } from '@/types/section'
import type { FiberLine } from '@/types/fiber'
import type { SectionStats } from '@/hooks/useSectionStats'
import type { FiberGroup, DirectionGroup } from './types'

type SectionListProps = {
    sections: FiberSection[]
    fibers: FiberLine[]
    sectionStats: Map<string, SectionStats>
    selectedSectionId: string | null
    onSelect: (sectionId: string, fiberId: string) => void
    onFlyTo: (sectionId: string, e: React.MouseEvent) => void
    onRename: (sectionId: string, name: string) => void
    onDelete: (sectionId: string) => void
    onToggleFavorite: (sectionId: string) => void
}

export function SectionList({
    sections,
    fibers,
    sectionStats,
    selectedSectionId,
    onSelect,
    onFlyTo,
    onRename,
    onDelete,
    onToggleFavorite,
}: SectionListProps) {
    const { t } = useTranslation()
    const [editingId, setEditingId] = useState<string | null>(null)
    const [editingName, setEditingName] = useState('')
    const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
    // Track which folders are expanded (empty = all collapsed by default)
    const [expandedFibers, setExpandedFibers] = useState<Set<string>>(new Set())
    const [expandedDirections, setExpandedDirections] = useState<Set<string>>(new Set())

    // Group sections by parent fiber, then by direction, with favorites at the top
    const groupedSections = useMemo(() => {
        const favorites = sections.filter(s => s.favorite)
        const regular = sections.filter(s => !s.favorite)

        // Build a map of fiberId -> fiber info
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

        const groups: FiberGroup<FiberSection>[] = []

        // Add favorites group if any exist
        if (favorites.length > 0) {
            const favByParent = new Map<string, Map<number, FiberSection[]>>()
            favorites.forEach(s => {
                const parent = getParentFiberId(s.fiberId)
                const dir = getDirection(s.fiberId)
                if (!favByParent.has(parent)) favByParent.set(parent, new Map())
                const dirMap = favByParent.get(parent)!
                if (!dirMap.has(dir)) dirMap.set(dir, [])
                dirMap.get(dir)!.push(s)
            })

            const favDirections: DirectionGroup<FiberSection>[] = []
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

        // Group regular sections by parent fiber, then direction
        const parentGroups = new Map<string, Map<number, FiberSection[]>>()
        regular.forEach(s => {
            const parent = getParentFiberId(s.fiberId)
            const dir = getDirection(s.fiberId)
            if (!parentGroups.has(parent)) parentGroups.set(parent, new Map())
            const dirMap = parentGroups.get(parent)!
            if (!dirMap.has(dir)) dirMap.set(dir, [])
            dirMap.get(dir)!.push(s)
        })

        // Convert to FiberGroup array
        const sortedParents = Array.from(parentGroups.keys()).sort()
        for (const parentId of sortedParents) {
            const dirMap = parentGroups.get(parentId)!
            const directions: DirectionGroup<FiberSection>[] = []

            const sortedDirs = Array.from(dirMap.keys()).sort()
            for (const dir of sortedDirs) {
                const items = dirMap.get(dir)!
                const fiberId = items[0]?.fiberId || `${parentId}:${dir}`
                directions.push({
                    direction: dir as 0 | 1,
                    fiberId,
                    items: items.sort((a, b) => a.startChannel - b.startChannel)
                })
            }

            const firstFiberId = directions[0]?.items[0]?.fiberId
            const fiberName = firstFiberId ? getFiberName(firstFiberId) : parentId

            groups.push({
                parentFiberId: parentId,
                fiberName,
                directions
            })
        }

        return groups
    }, [sections, fibers])

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

    const startEditing = useCallback((sectionId: string, currentName: string, e: React.MouseEvent) => {
        e.stopPropagation()
        setEditingId(sectionId)
        setEditingName(currentName)
    }, [])

    const saveName = useCallback((sectionId: string) => {
        onRename(sectionId, editingName)
        setEditingId(null)
    }, [onRename, editingName])

    const handleDelete = useCallback((sectionId: string, e: React.MouseEvent) => {
        e.stopPropagation()
        if (confirmDeleteId === sectionId) {
            onDelete(sectionId)
            setConfirmDeleteId(null)
        } else {
            setConfirmDeleteId(sectionId)
        }
    }, [confirmDeleteId, onDelete])

    const handleToggleFavorite = useCallback((sectionId: string, e: React.MouseEvent) => {
        e.stopPropagation()
        onToggleFavorite(sectionId)
    }, [onToggleFavorite])

    if (sections.length === 0) return null

    return (
        <div className="flex-shrink-0 border-b border-slate-100 max-h-48 overflow-y-auto">
            {groupedSections.map((group) => {
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

                                    {/* Sections in direction */}
                                    {(group.directions.length === 1 || isDirExpanded) && dirGroup.items.map(section => {
                                        const fullStats = sectionStats.get(section.id)
                                        const isSelected = selectedSectionId === section.id
                                        const totalVehicles = (fullStats?.direction0?.vehicleCount ?? 0) + (fullStats?.direction1?.vehicleCount ?? 0)
                                        const combinedSpeed = fullStats?.combined?.avgSpeed
                                        const isEditing = editingId === section.id
                                        const isConfirmingDelete = confirmDeleteId === section.id

                                        return (
                                            <div
                                                key={section.id}
                                                onClick={() => !isEditing && onSelect(section.id, section.fiberId)}
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
                                                                if (e.key === 'Enter') saveName(section.id)
                                                                if (e.key === 'Escape') setEditingId(null)
                                                            }}
                                                            onBlur={() => saveName(section.id)}
                                                            onClick={(e) => e.stopPropagation()}
                                                            autoFocus
                                                            className="w-full border border-slate-300 rounded px-1.5 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                        />
                                                    ) : (
                                                        <>
                                                            <div
                                                                className={`flex items-center gap-2 ${isSelected ? 'cursor-text' : ''}`}
                                                                onClick={(e) => {
                                                                    if (isSelected) {
                                                                        e.stopPropagation()
                                                                        startEditing(section.id, section.name, e)
                                                                    }
                                                                }}
                                                            >
                                                                {section.color && (
                                                                    <div
                                                                        className="w-2 h-2 rounded-full flex-shrink-0"
                                                                        style={{ backgroundColor: section.color }}
                                                                    />
                                                                )}
                                                                <span className={`text-sm font-medium truncate ${isSelected ? 'text-blue-700' : 'text-slate-700'}`}>
                                                                    {section.name}
                                                                </span>
                                                            </div>
                                                            <div className="text-[10px] text-slate-400">
                                                                {(fullStats?.distance ?? 0) >= 1000
                                                                    ? `${((fullStats?.distance ?? 0) / 1000).toFixed(1)} km`
                                                                    : `${fullStats?.distance ?? 0} m`
                                                                }
                                                            </div>
                                                        </>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
                                                    <div className={`flex items-center gap-0.5 ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}>
                                                        {/* Favorite button */}
                                                        <button
                                                            onClick={(e) => handleToggleFavorite(section.id, e)}
                                                            className={`p-1 transition-colors ${
                                                                section.favorite
                                                                    ? 'text-amber-500 hover:text-amber-600'
                                                                    : 'text-slate-300 hover:text-amber-500'
                                                            }`}
                                                            title={section.favorite ? t('traffic.landmarks.removeFromFavorites') : t('traffic.landmarks.addToFavorites')}
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill={section.favorite ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                                                            </svg>
                                                        </button>
                                                        {/* Fly to button */}
                                                        <button
                                                            onClick={(e) => onFlyTo(section.id, e)}
                                                            className="p-1 text-slate-400 hover:text-blue-500 transition-colors"
                                                            title={t('map.landmark.goToLocation')}
                                                        >
                                                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                                            </svg>
                                                        </button>
                                                        {/* Delete button */}
                                                        <button
                                                            onClick={(e) => handleDelete(section.id, e)}
                                                            onBlur={() => setConfirmDeleteId(null)}
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
                                                        <div className={`text-sm font-semibold ${combinedSpeed ? 'text-slate-700' : 'text-slate-300'}`}>
                                                            {combinedSpeed ? `${Math.round(combinedSpeed)}` : '—'}
                                                        </div>
                                                        <div className="text-[10px] text-slate-400">
                                                            {totalVehicles > 0 ? `${totalVehicles} ${t('traffic.landmarks.vehicleUnit')}` : ''}
                                                        </div>
                                                    </div>
                                                    {totalVehicles > 0 && combinedSpeed && (
                                                        <div className={`w-2 h-2 rounded-full ${getSpeedBgClass(combinedSpeed)}`} />
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
