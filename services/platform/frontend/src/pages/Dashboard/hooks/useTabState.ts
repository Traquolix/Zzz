import { useState } from 'react'

/** Incident tab local state (sort, calendar navigation). */
export function useIncidentTabState() {
  const [incidentSortBy, setIncidentSortBy] = useState<'newest' | 'oldest'>('newest')
  const todayStr = new Date().toISOString().slice(0, 10)
  const [selectedDate, setSelectedDate] = useState(todayStr)
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [calendarYear, setCalendarYear] = useState(new Date().getFullYear())
  const [calendarMonth, setCalendarMonth] = useState(new Date().getMonth() + 1)

  return {
    incidentSortBy,
    setIncidentSortBy,
    selectedDate,
    setSelectedDate,
    calendarOpen,
    setCalendarOpen,
    calendarYear,
    setCalendarYear,
    calendarMonth,
    setCalendarMonth,
  }
}

/** SHM tab local state (search filter). */
export function useShmTabState() {
  const [shmSearch, setShmSearch] = useState('')
  return { shmSearch, setShmSearch }
}

/** Sections tab local state (search filter). */
export function useSectionTabState() {
  const [sectionSearch, setSectionSearch] = useState('')
  return { sectionSearch, setSectionSearch }
}

type DataHubSubTab = 'export' | 'apiKeys'

/** Data hub tab local state (sub-tab, API key creation). */
export function useDataHubTabState() {
  const [dataHubSubTab, setDataHubSubTab] = useState<DataHubSubTab>('export')
  const [showCreateKey, setShowCreateKey] = useState(false)
  return { dataHubSubTab, setDataHubSubTab, showCreateKey, setShowCreateKey }
}
