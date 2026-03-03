import { useReducer, useEffect, useCallback, useState } from 'react'
import { cn } from '@/lib/utils'
import type { ProtoState, ProtoAction, Severity, Section } from './types'
import { initialSections, fibers } from './data'
import { PrototypeMap } from './components/PrototypeMap'
import { StatusBar } from './components/StatusBar'
import { Legend } from './components/Legend'
import { IncidentPanel } from './components/IncidentPanel'
import { SectionPanel } from './components/SectionPanel'
import { AnalysisView } from './components/AnalysisView'
import './prototype.css'

function generateHistory(base: number, variance: number, len: number): number[] {
    return Array.from({ length: len }, () =>
        Math.round(base + (Math.random() - 0.5) * 2 * variance)
    )
}

const initialState: ProtoState = {
    layer: 0,
    incidentPanelOpen: false,
    sectionPanelOpen: false,
    selectedIncidentId: null,
    selectedSectionId: null,
    filterSeverity: null,
    sections: initialSections,
    sectionCreationMode: false,
    pendingPoint: null,
    showNamingDialog: false,
    pendingSection: null,
}

function reducer(state: ProtoState, action: ProtoAction): ProtoState {
    switch (action.type) {
        case 'OPEN_INCIDENTS':
            return {
                ...state,
                layer: 1,
                incidentPanelOpen: true,
                sectionPanelOpen: false,
                selectedIncidentId: null,
                selectedSectionId: null,
                sectionCreationMode: false,
                pendingPoint: null,
            }
        case 'OPEN_SECTIONS':
            return {
                ...state,
                layer: 1,
                sectionPanelOpen: true,
                incidentPanelOpen: false,
                selectedIncidentId: null,
                selectedSectionId: null,
            }
        case 'CLOSE_PANELS':
            return {
                ...state,
                layer: 0,
                incidentPanelOpen: false,
                sectionPanelOpen: false,
                selectedIncidentId: null,
                selectedSectionId: null,
                filterSeverity: null,
            }
        case 'SELECT_INCIDENT':
            return {
                ...state,
                layer: 2,
                selectedIncidentId: action.id,
                selectedSectionId: null,
            }
        case 'SELECT_INCIDENT_FROM_MAP':
            return {
                ...state,
                layer: 2,
                incidentPanelOpen: true,
                sectionPanelOpen: false,
                selectedIncidentId: action.id,
                selectedSectionId: null,
                sectionCreationMode: false,
                pendingPoint: null,
            }
        case 'SELECT_SECTION':
            return {
                ...state,
                layer: 2,
                selectedSectionId: action.id,
                selectedIncidentId: null,
            }
        case 'BACK':
            return {
                ...state,
                layer: 1,
                selectedIncidentId: null,
                selectedSectionId: null,
            }
        case 'SET_FILTER_SEVERITY':
            return { ...state, filterSeverity: action.severity }
        case 'ENTER_SECTION_CREATION':
            return {
                ...state,
                sectionCreationMode: true,
                sectionPanelOpen: false,
                incidentPanelOpen: false,
                layer: 0,
                pendingPoint: null,
                selectedIncidentId: null,
                selectedSectionId: null,
            }
        case 'EXIT_SECTION_CREATION':
            return {
                ...state,
                sectionCreationMode: false,
                pendingPoint: null,
                showNamingDialog: false,
                pendingSection: null,
            }
        case 'SET_PENDING_POINT':
            return { ...state, pendingPoint: action.point }
        case 'OPEN_NAMING_DIALOG':
            return {
                ...state,
                showNamingDialog: true,
                pendingSection: { fiberId: action.fiberId, startChannel: action.startChannel, endChannel: action.endChannel },
                sectionCreationMode: false,
                pendingPoint: null,
            }
        case 'CLOSE_NAMING_DIALOG':
            return {
                ...state,
                showNamingDialog: false,
                pendingSection: null,
            }
        case 'CREATE_SECTION':
            return {
                ...state,
                sections: [...state.sections, action.section],
                showNamingDialog: false,
                pendingSection: null,
                sectionCreationMode: false,
                pendingPoint: null,
            }
        case 'DELETE_SECTION':
            return {
                ...state,
                sections: state.sections.filter((s) => s.id !== action.id),
                selectedSectionId: state.selectedSectionId === action.id ? null : state.selectedSectionId,
                layer: state.selectedSectionId === action.id ? 1 : state.layer,
            }
        default:
            return state
    }
}

export function Prototype() {
    const [state, dispatch] = useReducer(reducer, initialState)

    const handleIncidentClick = useCallback((id: string) => {
        dispatch({ type: 'SELECT_INCIDENT_FROM_MAP', id })
    }, [])

    // Keyboard shortcuts
    useEffect(() => {
        function onKeyDown(e: KeyboardEvent) {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

            if (e.key === 'i') {
                dispatch({ type: 'OPEN_INCIDENTS' })
            } else if (e.key === 's' && !state.sectionCreationMode) {
                dispatch({ type: 'OPEN_SECTIONS' })
            } else if (e.key === 'c') {
                if (state.sectionCreationMode) {
                    dispatch({ type: 'EXIT_SECTION_CREATION' })
                } else {
                    dispatch({ type: 'ENTER_SECTION_CREATION' })
                }
            } else if (e.key === 'Escape') {
                if (state.showNamingDialog) {
                    dispatch({ type: 'CLOSE_NAMING_DIALOG' })
                } else if (state.sectionCreationMode) {
                    dispatch({ type: 'EXIT_SECTION_CREATION' })
                } else if (state.layer === 2) {
                    dispatch({ type: 'BACK' })
                } else if (state.layer === 1) {
                    dispatch({ type: 'CLOSE_PANELS' })
                }
            }
        }

        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [state.layer, state.sectionCreationMode, state.showNamingDialog])

    const isAnalysisOpen = state.layer === 2

    return (
        <div className="prototype w-screen h-screen flex overflow-hidden">
            {/* Map area */}
            <div
                className={cn(
                    'proto-map-wrapper relative h-full',
                    isAnalysisOpen ? 'w-[45%]' : 'w-full',
                )}
            >
                <PrototypeMap
                    onIncidentClick={handleIncidentClick}
                    sectionCreationMode={state.sectionCreationMode}
                    pendingPoint={state.pendingPoint}
                    sections={state.sections}
                    onFiberClick={(point) => dispatch({ type: 'SET_PENDING_POINT', point })}
                    onSectionComplete={(fiberId, startChannel, endChannel) =>
                        dispatch({ type: 'OPEN_NAMING_DIALOG', fiberId, startChannel, endChannel })
                    }
                />

                {/* Section creation banner */}
                {state.sectionCreationMode && (
                    <div className="proto-creation-banner absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 px-4 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-sm text-amber-200">
                        <span>
                            {state.pendingPoint
                                ? 'Click another point on the same cable to complete the section'
                                : 'Click on a fiber to set the start point'}
                        </span>
                        <button
                            onClick={() => dispatch({ type: 'EXIT_SECTION_CREATION' })}
                            className="text-xs px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 transition-colors cursor-pointer"
                        >
                            Cancel
                        </button>
                    </div>
                )}

                {/* Layer 0 overlays */}
                <StatusBar
                    sections={state.sections}
                    onOpenIncidents={() => dispatch({ type: 'OPEN_INCIDENTS' })}
                    onOpenSections={() => dispatch({ type: 'OPEN_SECTIONS' })}
                />
                {!isAnalysisOpen && <Legend />}

                {/* Layer 1 panels */}
                <IncidentPanel
                    open={state.incidentPanelOpen}
                    filterSeverity={state.filterSeverity}
                    onFilterChange={(severity: Severity | null) =>
                        dispatch({ type: 'SET_FILTER_SEVERITY', severity })
                    }
                    onSelectIncident={(id: string) => dispatch({ type: 'SELECT_INCIDENT', id })}
                    onClose={() => dispatch({ type: 'CLOSE_PANELS' })}
                />
                <SectionPanel
                    open={state.sectionPanelOpen}
                    sections={state.sections}
                    onSelectSection={(id: string) => dispatch({ type: 'SELECT_SECTION', id })}
                    onAddSection={() => dispatch({ type: 'ENTER_SECTION_CREATION' })}
                    onDeleteSection={(id: string) => dispatch({ type: 'DELETE_SECTION', id })}
                    onClose={() => dispatch({ type: 'CLOSE_PANELS' })}
                />
            </div>

            {/* Layer 2 analysis view */}
            {isAnalysisOpen && (
                <div className="flex-1 h-full border-l border-[var(--proto-border)]">
                    <AnalysisView
                        sections={state.sections}
                        selectedIncidentId={state.selectedIncidentId}
                        selectedSectionId={state.selectedSectionId}
                        onBack={() => dispatch({ type: 'BACK' })}
                    />
                </div>
            )}

            {/* Naming dialog overlay */}
            {state.showNamingDialog && state.pendingSection && (
                <NamingDialog
                    pendingSection={state.pendingSection}
                    onSave={(name) => {
                        const ps = state.pendingSection!
                        const fiber = fibers.find((f) => f.id === ps.fiberId)
                        const section: Section = {
                            id: `section:${ps.fiberId}:${ps.startChannel}-${ps.endChannel}`,
                            fiberId: ps.fiberId,
                            name,
                            startChannel: ps.startChannel,
                            endChannel: ps.endChannel,
                            avgSpeed: 60 + Math.round(Math.random() * 40),
                            flow: 500 + Math.round(Math.random() * 1500),
                            occupancy: 10 + Math.round(Math.random() * 40),
                            travelTime: 1 + Math.round(Math.random() * 8 * 10) / 10,
                            speedHistory: generateHistory(70, 15, 30),
                            countHistory: generateHistory(1000, 200, 30),
                        }
                        void fiber // used in id generation context
                        dispatch({ type: 'CREATE_SECTION', section })
                    }}
                    onCancel={() => dispatch({ type: 'CLOSE_NAMING_DIALOG' })}
                />
            )}
        </div>
    )
}

function NamingDialog({
    pendingSection,
    onSave,
    onCancel,
}: {
    pendingSection: { fiberId: string; startChannel: number; endChannel: number }
    onSave: (name: string) => void
    onCancel: () => void
}) {
    const [name, setName] = useState('')
    const fiber = fibers.find((f) => f.id === pendingSection.fiberId)

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-[var(--proto-surface)] border border-[var(--proto-border)] rounded-lg p-5 w-[360px] shadow-2xl">
                <h3 className="text-sm font-semibold text-[var(--proto-text)] mb-1">Name this section</h3>
                <p className="text-xs text-[var(--proto-text-muted)] mb-4">
                    {fiber?.name} · Ch {pendingSection.startChannel} - {pendingSection.endChannel}
                </p>
                <input
                    autoFocus
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && name.trim()) onSave(name.trim())
                    }}
                    placeholder="e.g. Zone Nord"
                    className="w-full px-3 py-2 rounded-md bg-[var(--proto-base)] border border-[var(--proto-border)] text-sm text-[var(--proto-text)] placeholder:text-[var(--proto-text-muted)] outline-none focus:border-[var(--proto-accent)] mb-4"
                />
                <div className="flex justify-end gap-2">
                    <button
                        onClick={onCancel}
                        className="px-3 py-1.5 rounded text-xs text-[var(--proto-text-secondary)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => name.trim() && onSave(name.trim())}
                        disabled={!name.trim()}
                        className="px-3 py-1.5 rounded text-xs bg-[var(--proto-accent)] text-white disabled:opacity-40 cursor-pointer hover:bg-[var(--proto-accent)]/80 transition-colors"
                    >
                        Create
                    </button>
                </div>
            </div>
        </div>
    )
}

export default Prototype
