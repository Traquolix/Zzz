import { useLocation, useOutlet } from 'react-router-dom'
import { useRef, useEffect, useState } from 'react'

export function PageTransition() {
    const location = useLocation()
    const outlet = useOutlet()
    const [displayedOutlet, setDisplayedOutlet] = useState(outlet)
    const [isVisible, setIsVisible] = useState(true)
    const prevPathRef = useRef(location.pathname)

    useEffect(() => {
        if (location.pathname !== prevPathRef.current) {
            // New route: fade out and replace content
            setIsVisible(false)
            // Small delay to trigger CSS transition
            const timer = setTimeout(() => {
                setDisplayedOutlet(outlet)
                setIsVisible(true)
                prevPathRef.current = location.pathname
            }, 50) // Very brief, just enough for reflow
            return () => clearTimeout(timer)
        }
    }, [location.pathname, outlet])

    return (
        <div
            className={`flex-1 flex flex-col min-h-0 transition-opacity duration-200 ease-out ${
                isVisible ? 'opacity-100' : 'opacity-0'
            }`}
            id="main-content"
        >
            {displayedOutlet}
        </div>
    )
}
