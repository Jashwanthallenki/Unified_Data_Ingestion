export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface IngestionBatch {
  id: string;
  tenant: string;
  source_type: "sap" | "utility" | "travel";
  ingestion_method: "FILE_UPLOAD" | "API_PULL";
  original_filename: string | null;
  api_sync_range_start: string | null;
  api_sync_range_end: string | null;
  uploaded_at: string;
  status: "PROCESSING" | "COMPLETE" | "FAILED" | "PARTIAL";
  total_rows: number;
  raw_rows_stored: number;
  eligible_rows: number;
  excluded_rows: number;
  not_relevant_rows: number;
  failed_rows: number;
  successful_rows: number;
  flagged_rows: number;
  suspicious_rows: number;
  low_confidence_rows: number;
  llm_suggested_rows: number;
  pending_rows: number;
  approved_rows: number;
  rejected_rows: number;
  locked_rows: number;
  plant_lookup_version: string | null;
  material_lookup_version: string | null;
  unit_mapping_version: string | null;
  meter_mapping_version: string | null;
  ef_version: string | null;
  notes: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RawRecord {
  id: string;
  batch: string;
  source_type: string;
  row_number: number;
  raw_payload: Record<string, unknown>;
  parse_status: "PARSED" | "FAILED" | "EXCLUDED";
  eligibility_status: string | null;
  exclusion_reason: string | null;
  error_message: string | null;
  created_at: string;
}

export interface ValidationIssue {
  id: string;
  issue_code: string;
  severity: "ERROR" | "WARNING" | "INFO";
  message: string;
  created_at: string;
}

export interface ReviewLogEntry {
  id: string;
  action: string;
  reviewer: number | null;
  reviewer_username: string | null;
  comment: string | null;
  old_value: unknown;
  new_value: unknown;
  created_at: string;
}

export interface LlmSuggestion {
  field: string;
  suggested_value: unknown;
  confidence: number;
  reason: string;
  method: string;
}

export interface NormalizedActivity {
  id: string;
  batch: string;
  source_type: "sap" | "utility" | "travel";
  activity_type: string;
  activity_subtype: string | null;
  scope: number | null;
  scope_category: string | null;
  eligibility_status: string;
  review_status: string;
  activity_basis: string | null;
  calculation_method: string | null;
  emission_method: string | null;
  source_hierarchy_rank: number | null;
  source_of_truth: string | null;
  activity_date: string | null;
  period_start: string | null;
  period_end: string | null;
  calendar_month: string | null;
  billing_days: number | null;
  facility_code: string | null;
  facility_name: string | null;
  facility_country: string | null;
  origin: string | null;
  destination: string | null;
  quantity: string | null;
  unit: string | null;
  normalized_quantity: string | null;
  normalized_unit: string | null;
  usage_per_day: string | null;
  currency: string | null;
  amount: string | null;
  vendor: string | null;
  cost_center: string | null;
  reference_id: string | null;
  is_duplicate: boolean;
  is_reversal: boolean;
  is_estimate: boolean;
  requires_reconciliation: boolean;
  emission_factor: string | null;
  emission_factor_source: string | null;
  co2e_kg: string | null;
  data_quality_score: number;
  confidence_level: "HIGH" | "MEDIUM" | "LOW" | "FAILED";
  method_confidence: string | null;
  flags: string[];
  llm_suggestion_reviewed: boolean;
  approved_at: string | null;
  locked_at: string | null;
  issue_count: number;
  created_at: string;
}

export interface NormalizedActivityDetail extends NormalizedActivity {
  field_provenance: Record<string, { method: string; rule?: string; confidence?: number; reason?: string; source_field?: string; note?: string }>;
  llm_suggestions: LlmSuggestion[];
  review_comment: string | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
  approved_by: number | null;
  locked_snapshot: Record<string, unknown> | null;
  issues: ValidationIssue[];
  review_logs: ReviewLogEntry[];
  raw_payload: Record<string, unknown>;
}

export interface ReviewSummary {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  clarification_requested: number;
  marked_not_relevant: number;
  locked: number;
  high_confidence: number;
  medium_confidence: number;
  low_confidence: number;
  failed_confidence: number;
  suspicious: number;
  llm_suggested: number;
  estimated: number;
  spend_based: number;
  by_source: { sap: number; utility: number; travel: number };
}

export interface ExclusionRow {
  id: string;
  row_number: number;
  exclusion_reason: string;
  parse_status: string;
  eligibility_status: string | null;
  raw_payload: Record<string, unknown>;
}

export interface GroqSuggestResponse {
  ok: boolean;
  cached?: boolean;
  model?: string;
  error?: string;
  suggestions?: LlmSuggestion[];
  notes?: string[];
}
