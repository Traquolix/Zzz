import type { ReactNode } from 'react'
import { MapInstanceProvider } from './MapInstanceProvider'
import { MapSelectionProvider } from './MapSelectionProvider'
import { SectionDataProvider } from './SectionProvider'
import { SectionUIProvider } from './SectionUIProvider'
import { LandmarkDataProvider } from './LandmarkSelectionProvider'
import { VehicleDataProvider } from './VehicleSelectionProvider'
import { InfrastructureDataProvider } from './InfrastructureProvider'

/**
 * Composite provider that wraps all dashboard-scoped data providers.
 * Reduces nesting in Dashboard.tsx from 6 levels to 2.
 *
 * Provider order (inner to outer):
 * - InfrastructureDataProvider (needs MapSelectionProvider)
 * - VehicleDataProvider (needs MapSelectionProvider)
 * - LandmarkDataProvider (needs MapSelectionProvider)
 * - SectionDataProvider (needs MapSelectionProvider)
 * - MapSelectionProvider (standalone selection state)
 * - MapInstanceProvider (standalone map instance)
 */
export function DashboardDataProvider({ children }: { children: ReactNode }) {
    return (
        <MapInstanceProvider>
            <MapSelectionProvider>
                <SectionDataProvider>
                <SectionUIProvider>
                    <LandmarkDataProvider>
                        <VehicleDataProvider>
                            <InfrastructureDataProvider>
                                {children}
                            </InfrastructureDataProvider>
                        </VehicleDataProvider>
                    </LandmarkDataProvider>
                </SectionUIProvider>
                </SectionDataProvider>
            </MapSelectionProvider>
        </MapInstanceProvider>
    )
}
