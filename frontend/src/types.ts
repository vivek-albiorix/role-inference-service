// Mirrors app/models/schemas.py -- the Pydantic DTOs at the API boundary.
// Keep in sync by hand; there are few enough of these that codegen isn't
// worth the extra tooling at this scale.

export type Source = 'okta' | 'entra' | 'google' | 'unknown'
export type Band = 'high' | 'medium' | 'low' | 'very_low'

export interface SSOProfileIn {
  user_id: string
  display_name?: string | null
  title?: string | null
  department?: string | null
  manager_title?: string | null
  groups?: string[]
  skills?: string[]
  location?: string | null
  notes?: string | null
  source?: Source
}

export interface ProfileIngestedOut {
  user_id: string
  profile_version: number
  inference_run_id: number
}

export interface RoleOut {
  role_id: string
  role_name: string
  department: string
  job_family: string
  seniority: string
  skills: string[]
  keywords: string[]
}

export interface RoleIn {
  role_name: string
  department: string
  job_family: string
  seniority: string
  skills?: string[]
  keywords?: string[]
}

export interface SignalEvidence {
  signal: string
  value: unknown
  weight: number
  supports: boolean
}

export interface AlternativeRole {
  role: string
  role_id: string
  confidence: number
  why_lost: string | null
}

export interface InferenceResultOut {
  run_id: number
  user_id: string
  profile_version: number
  catalog_version: number
  inferred_role: string | null
  role_id: string | null
  confidence: number
  band: Band
  explanation: string
  signals: string[]
  alternative_roles: AlternativeRole[]
  signals_used: SignalEvidence[]
  positive_evidence: string[]
  negative_evidence: string[]
  why_winner_won: string | null
  missing_information: string[]
  llm_used: boolean
  llm_degraded: boolean
  llm_cached: boolean
  stage_timings_ms: Record<string, number>
  engine_version: string
  prompt_version: string
  created_at: string
}

export interface EffectiveRoleOut {
  role_id: string | null
  role_name: string | null
  source: 'inferred' | 'overridden'
  confidence: number | null
  band: string | null
  override_reason: string | null
}

export interface UserSummaryOut {
  user_id: string
  display_name: string | null
  title: string | null
  department: string | null
  effective_role: EffectiveRoleOut
  override_active: boolean
  override_pinned: boolean
}

export interface OverrideIn {
  role_id: string
  pinned: boolean
  reason?: string | null
  created_by?: string
}

export interface OverrideOut {
  id: number
  role_id: string
  pinned: boolean
  reason: string | null
  created_by: string
  created_at: string
  active: boolean
}

export interface ReprocessStartedOut {
  status: 'started'
}

export type ReprocessJobState = 'idle' | 'running' | 'completed' | 'failed'

export interface ReprocessStatusOut {
  state: ReprocessJobState
  started_at: string | null
  finished_at: string | null
  processed_count: number
  skipped_pinned_count: number
  user_ids_processed: string[]
  user_ids_skipped: string[]
  error: string | null
}
