export interface Job {
  id: number
  title: string
  company: string
  description: string
  description_full?: string
  link: string
  source: string
  match_score: number
  ats_score?: number | null
  status: JobStatus
  pipeline_stage: PipelineStage
  location?: string
  date_posted?: string
  remote: boolean
  h1b_mention: boolean
  salary_text?: string
  contact_email?: string
  scraped_at?: string
  applied_at?: string
  search_query?: string
  /** Set when the user clicks Apply in the dashboard. Drives the did-you-apply modal. */
  apply_intent_at?: string | null
  /** Set when the user answers Yes/No to the did-you-apply modal. */
  apply_intent_acknowledged_at?: string | null
}

export type JobStatus =
  | "shortlisted"
  | "applied_email"
  | "applied_link"
  | "following_up"
  | "interview"
  | "offer"
  | "skipped"
  | "no_email"

export type PipelineStage = "saved" | "applied" | "following_up" | "interview" | "skipped"

export interface JobStats {
  total: number
  shortlisted: number
  applied_total: number
  following_up: number
  interview: number
  offer: number
  skipped: number
  h1b: number
  remote: number
}

export interface BoardInfo {
  name: string
  label: string
  color: string
  tag: string
  tier: 1 | 2 | 3
  configured: boolean
  hint: string
  remote_only: boolean
}

export interface ATSScanResult {
  ats_score: number
  keyword_score: number
  semantic_score: number
  found_keywords: string[]
  /** New in Phase 3a — keywords semantically covered without an exact word match. */
  implied_keywords?: string[]
  missing_keywords: string[]
  missing_by_section: Record<string, string[]>
  resume_sections: string[]
  nlp_mode: "keybert" | "vocabulary"
  suggestions: ATSSuggestion[]
  bullet_rewrites: BulletRewrite[]
  /** LLM-generated tailored summary, or null if not produced. */
  summary_rewrite?: SummaryRewrite | null
}

export interface SummaryRewrite {
  type: "summary_rewrite"
  section: "summary"
  original: string
  rewrite: string
  engine: "llm" | "template"
  /** True when the resume had no Summary section and we're proposing a NEW one. */
  is_new: boolean
}

export interface ATSSuggestion {
  priority: "high" | "medium" | "low"
  section: string
  category: string
  suggestion: string
}

export interface BulletRewrite {
  keyword: string
  original: string
  rewrite: string
  added_text: string
  section: string
  score: number
  /** "llm" when Ollama produced the rewrite; "template" for the deterministic fallback. */
  engine?: "llm" | "template"
  type: "rewrite"
}

export interface Resume {
  filename: string
  text: string
  skills: string[]
  uploaded_at: string
}

export interface SearchRequest {
  keywords: string
  location: string
  boards: string[]
  num_per_board: number
  date_filter?: number | null
  job_type?: string | null
  h1b_only: boolean
  hide_old: boolean
  replace_existing: boolean
}

export interface SearchResponse {
  total_saved: number
  experience_years: number
  experience_method: "explicit" | "calculated" | "unknown"
  jobs: Job[]
}

export interface ExperienceInfo {
  years: number
  level: "intern" | "entry" | "mid" | "senior"
  method: "explicit" | "calculated" | "unknown"
}

export interface ClearDataRequest {
  include_resume: boolean
}

export interface ClearDataResponse {
  ok: boolean
  jobs_deleted: number
  resumes_deleted: number
}
