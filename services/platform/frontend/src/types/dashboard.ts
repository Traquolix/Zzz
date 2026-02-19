import type { ComponentType } from "react"
import type { Layout } from 'react-grid-layout'

export type Layouts = Partial<Record<string, Layout>>

export type WidgetConfig = {
    id: string
    name: string
    component: ComponentType
}