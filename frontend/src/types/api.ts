export interface SiteItem {
  site: string
  business_unit: string | null
  incident_count: number
}

export interface KPIResponse {
  quarter: string
  site: string | null
  total_incidents_qtr: number
  delta_vs_last_qtr_pct: number | null
  top_category: string | null
  top_category_share: number | null
  predicted_next_qtr: number | null
  risk_score: number | null
  confidence_score: number | null
}

export interface IncidentTypeCount {
  incident_type: string
  count: number
}

export interface IncidentCategoryCount {
  category: string
  count: number
}

export interface IncidentSiteCount {
  site: string
  business_unit: string | null
  count: number
}

export interface TrendPoint {
  year: number
  month: number
  month_label: string
  count: number
  all_sites_avg: number
}

export interface HeatmapPoint {
  site: string
  business_unit: string | null
  likelihood_score: number
  impact_score: number
  risk_band: string
}

export interface DriverItem {
  id: number
  site: string
  quarter: string
  driver_name: string | null
  category: string | null
  impact_score: number | null
  trend: string | null
  pct_change_vs_last_qtr: number | null
  computed_at: string | null
}

export interface RecommendationItem {
  id: number
  site: string
  quarter: string
  action_text: string | null
  priority: string | null
  impact_estimate: string | null
  suggested_owner: string | null
  status: string | null
  source: string | null
  created_at: string | null
}

export interface PredictionItem {
  id: number
  site: string
  business_unit: string | null
  target_quarter: string
  predicted_count: number | null
  lower_ci: number | null
  upper_ci: number | null
  model_name: string | null
  trained_at: string | null
  training_data_through: string | null
  confidence_band: string | null
}

export interface ModelMeta {
  site: string
  champion_model: string | null
  holdout_rmse: number | null
  holdout_mape: number | null
  training_rows: number | null
  last_trained_at: string | null
  n_quarters_history: number | null
}

export interface PredictionsResponse {
  model_meta: ModelMeta
  predictions: PredictionItem[]
}

export interface BacktestPoint {
  month: string
  actual: number | null
  predicted: number | null
  model_name: string | null
}

export interface RiskScoreItem {
  id: number
  site: string
  business_unit: string | null
  quarter: string
  quarter_sort_key: number | null
  risk_score: number | null
  risk_level: string | null
  frequency_index: number | null
  severity_index: number | null
  velocity_index: number | null
  diversity_index: number | null
  computed_at: string | null
}

export interface FreshnessResponse {
  last_pipeline_run_at: string | null
  pipeline_run_status: string | null
  latest_data_date: string | null
  latest_predicted_quarter: string | null
  last_ingest_at: string | null
}
