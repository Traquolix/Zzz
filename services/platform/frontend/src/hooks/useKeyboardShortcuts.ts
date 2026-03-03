import { useEffect, useRef } from 'react'

export type ShortcutHandler = () => void
export type ShortcutCombo = string // e.g., 'Escape', 'ctrl+k', 'shift+?'

export type ShortcutRegistration = {
    combo: ShortcutCombo
    handler: ShortcutHandler
    /** If true, fires even when focus is in an input/textarea */
    global?: boolean
    /** Description for help display */
    description?: string
}

// Module-level registry mapping combo -> Set of registrations
const shortcutRegistry = new Map<string, Set<ShortcutRegistration>>()

// Normalize a combo string for comparison
function normalizeCombo(combo: string): string {
    // Convert to lowercase and handle ctrl/meta normalization
    return combo.toLowerCase().replace(/\bctrl\b/g, 'meta')
}

// Check if the current active element should block shortcuts
function isInputFocused(): boolean {
    const activeElement = document.activeElement
    if (activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement) {
        return true
    }
    if (activeElement && activeElement.getAttribute('contenteditable') === 'true') {
        return true
    }
    return false
}

// Convert a KeyboardEvent to a combo string
function eventToCombo(event: KeyboardEvent): string {
    const parts: string[] = []

    if (event.ctrlKey && !event.metaKey) {
        parts.push('ctrl')
    }
    if (event.metaKey) {
        parts.push('meta')
    }
    if (event.altKey) {
        parts.push('alt')
    }
    if (event.shiftKey) {
        parts.push('shift')
    }

    // Add the key itself
    const key = event.key.toLowerCase()
    parts.push(key)

    return parts.join('+')
}

// Global keydown listener
function handleKeydown(event: KeyboardEvent) {
    // Special case: Escape always fires
    if (event.key === 'Escape') {
        const registrations = shortcutRegistry.get(normalizeCombo('Escape'))
        if (registrations) {
            registrations.forEach(reg => {
                reg.handler()
            })
        }
        return
    }

    const isInput = isInputFocused()
    const eventCombo = normalizeCombo(eventToCombo(event))

    // Find matching registrations
    const registrations = shortcutRegistry.get(eventCombo)
    if (!registrations) return

    registrations.forEach(reg => {
        // Skip if input is focused and not global
        if (isInput && !reg.global) {
            return
        }
        reg.handler()
    })
}

// Hook to register a keyboard shortcut
export function useKeyboardShortcut(registration: ShortcutRegistration): void {
    const normalizedCombo = normalizeCombo(registration.combo)
    // Use a stable ref so the registration object identity doesn't cause re-subscriptions
    const regRef = useRef(registration)
    regRef.current = registration

    // Stable registration that delegates to the ref
    const stableReg = useRef<ShortcutRegistration>({
        combo: registration.combo,
        handler: () => regRef.current.handler(),
        global: registration.global,
        description: registration.description,
    })

    useEffect(() => {
        const reg = stableReg.current

        // Add listener on first registration
        if (shortcutRegistry.size === 0) {
            document.addEventListener('keydown', handleKeydown)
        }

        // Register this shortcut
        if (!shortcutRegistry.has(normalizedCombo)) {
            shortcutRegistry.set(normalizedCombo, new Set())
        }
        shortcutRegistry.get(normalizedCombo)!.add(reg)

        // Cleanup
        return () => {
            const registrations = shortcutRegistry.get(normalizedCombo)
            if (registrations) {
                registrations.delete(reg)
                if (registrations.size === 0) {
                    shortcutRegistry.delete(normalizedCombo)
                }
            }

            // Remove listener if no more registrations
            if (shortcutRegistry.size === 0) {
                document.removeEventListener('keydown', handleKeydown)
            }
        }
    }, [normalizedCombo])
}

