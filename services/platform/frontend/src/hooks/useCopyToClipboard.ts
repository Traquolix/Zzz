import { useState, useCallback, useRef, useEffect } from 'react'

export function useCopyToClipboard(resetDelay = 2000) {
    const [copiedText, setCopiedText] = useState<string | null>(null)
    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Clear pending timer on unmount
    useEffect(() => {
        return () => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current)
        }
    }, [])

    const copy = useCallback(async (text: string): Promise<boolean> => {
        try {
            await navigator.clipboard.writeText(text)
            setCopiedText(text)
            if (timeoutRef.current) clearTimeout(timeoutRef.current)
            timeoutRef.current = setTimeout(() => setCopiedText(null), resetDelay)
            return true
        } catch {
            // Fallback for older browsers
            try {
                const textArea = document.createElement('textarea')
                textArea.value = text
                textArea.style.position = 'fixed'
                textArea.style.opacity = '0'
                document.body.appendChild(textArea)
                textArea.select()
                document.execCommand('copy')
                document.body.removeChild(textArea)
                setCopiedText(text)
                if (timeoutRef.current) clearTimeout(timeoutRef.current)
                timeoutRef.current = setTimeout(() => setCopiedText(null), resetDelay)
                return true
            } catch {
                return false
            }
        }
    }, [resetDelay])

    const isCopied = useCallback((text: string) => copiedText === text, [copiedText])

    /** Backwards-compatible: true when anything was just copied */
    const copied = copiedText !== null

    return { copy, copied, isCopied }
}
