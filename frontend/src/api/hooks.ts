import { useQuery } from '@tanstack/react-query'
import apiClient from './client'
import type {
  SiteItem,
  KPIResponse,
  IncidentTypeCount,
  IncidentCategoryCount,
  IncidentSiteCount,
  TrendPoint,
  HeatmapPoint,
  DriverItem,
  RecommendationItem,
  PredictionsResponse,
  BacktestPoint,
  RiskScoreItem,
  FreshnessResponse,
  DiagnosticsResponse,
} from '@/types/api'

const q5m = { staleTime: 5 * 60_000, gcTime: 10 * 60_000 }

// ---------- helper ----------
function get<T>(url: string, params?: Record<string, string | number | undefined>) {
  return apiClient.get<T>(url, { params }).then((r) => r.data)
}

// ---------- hooks ----------

export function useSites(quarter?: string) {
  return useQuery({
    queryKey: ['sites', quarter],
    queryFn: () => get<SiteItem[]>('/api/sites', { quarter }),
    ...q5m,
  })
}

export function useKpis(site?: string, quarter?: string) {
  return useQuery({
    queryKey: ['kpis', site, quarter],
    queryFn: () => get<KPIResponse>('/api/kpis', { site, quarter }),
    enabled: !!site,
    ...q5m,
  })
}

export function useIncidentsByType(site?: string, quarter?: string) {
  return useQuery({
    queryKey: ['incidents-by-type', site, quarter],
    queryFn: () => get<IncidentTypeCount[]>('/api/incidents/by-type', { site, quarter }),
    enabled: !!site,
    ...q5m,
  })
}

export function useIncidentsByCategory(site?: string, quarter?: string) {
  return useQuery({
    queryKey: ['incidents-by-category', site, quarter],
    queryFn: () => get<IncidentCategoryCount[]>('/api/incidents/by-category', { site, quarter }),
    enabled: !!site,
    ...q5m,
  })
}

export function useIncidentsBySite(quarter?: string, businessUnit?: string) {
  return useQuery({
    queryKey: ['incidents-by-site', quarter, businessUnit],
    queryFn: () =>
      get<IncidentSiteCount[]>('/api/incidents/by-site', { quarter, business_unit: businessUnit }),
    ...q5m,
  })
}

export function useIncidentTrend(site?: string, months = 12) {
  return useQuery({
    queryKey: ['incident-trend', site, months],
    queryFn: () => get<TrendPoint[]>('/api/incidents/trend', { site, months }),
    enabled: !!site,
    ...q5m,
  })
}

export function useHeatmap(quarter?: string) {
  return useQuery({
    queryKey: ['heatmap', quarter],
    queryFn: () => get<HeatmapPoint[]>('/api/incidents/heatmap', { quarter }),
    ...q5m,
  })
}

export function useDrivers(site?: string, quarter?: string) {
  return useQuery({
    queryKey: ['drivers', site, quarter],
    queryFn: () => get<DriverItem[]>('/api/drivers', { site, quarter }),
    enabled: !!site,
    ...q5m,
  })
}

export function useRecommendations(site?: string, quarter?: string) {
  return useQuery({
    queryKey: ['recommendations', site, quarter],
    queryFn: () => get<RecommendationItem[]>('/api/recommendations', { site, quarter }),
    enabled: !!site,
    ...q5m,
  })
}

export function usePredictions(site?: string) {
  return useQuery({
    queryKey: ['predictions', site],
    queryFn: () => get<PredictionsResponse>('/api/predictions', { site }),
    enabled: !!site,
    ...q5m,
  })
}

export function useBacktest(site?: string) {
  return useQuery({
    queryKey: ['backtest', site],
    queryFn: () => get<BacktestPoint[]>('/api/predictions/backtest', { site }),
    enabled: !!site,
    ...q5m,
  })
}

export function useRiskScores(site?: string, quarter?: string) {
  return useQuery({
    queryKey: ['risk-scores', site, quarter],
    queryFn: () =>
      get<RiskScoreItem[]>('/api/risk-scores', {
        site,
        quarter,
        latest_only: site ? undefined : 1,
      }),
    ...q5m,
  })
}

export function useFreshness() {
  return useQuery({
    queryKey: ['freshness'],
    queryFn: () => get<FreshnessResponse>('/api/admin/freshness'),
    staleTime: 60_000,
    refetchInterval: 2 * 60_000,
  })
}

export function useDiagnostics() {
  return useQuery({
    queryKey: ['diagnostics'],
    queryFn: () => get<DiagnosticsResponse>('/api/admin/diagnostics'),
    staleTime: 60_000,
  })
}
