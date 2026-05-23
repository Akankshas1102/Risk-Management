import React, { createContext, useContext, useState, useEffect } from 'react'
import { defaultQuarter } from '@/lib/utils'
import { useSites } from '@/api/hooks'

interface FilterState {
  selectedSite: string
  setSelectedSite: (site: string) => void
  selectedQuarter: string
  setSelectedQuarter: (q: string) => void
}

const FilterContext = createContext<FilterState | null>(null)

export function FilterProvider({ children }: { children: React.ReactNode }) {
  const [selectedSite, setSelectedSite] = useState<string>('')
  const [selectedQuarter, setSelectedQuarter] = useState<string>(defaultQuarter())

  const sitesQuery = useSites(selectedQuarter)

  // Auto-select the first site once data loads
  useEffect(() => {
    if (!selectedSite && sitesQuery.data && sitesQuery.data.length > 0) {
      setSelectedSite(sitesQuery.data[0].site)
    }
  }, [sitesQuery.data, selectedSite])

  return (
    <FilterContext.Provider
      value={{ selectedSite, setSelectedSite, selectedQuarter, setSelectedQuarter }}
    >
      {children}
    </FilterContext.Provider>
  )
}

export function useFilters(): FilterState {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilters must be used inside FilterProvider')
  return ctx
}
