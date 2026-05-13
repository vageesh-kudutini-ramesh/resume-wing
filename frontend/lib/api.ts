import axios from "axios"
import type {
  Job, JobStats, BoardInfo, ATSScanResult, Resume,
  SearchRequest, SearchResponse, ExperienceInfo,
  ClearDataRequest, ClearDataResponse,
} from "./types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

const api = axios.create({ baseURL: API_BASE })

// ── Health ─────────────────────────────────────────────────────────────────────
export const checkHealth = () => api.get("/health").then(r => r.data)

// ── Boards ─────────────────────────────────────────────────────────────────────
export const getBoards = (): Promise<BoardInfo[]> =>
  api.get("/boards/status").then(r => r.data)

// ── Jobs ───────────────────────────────────────────────────────────────────────
export const searchAndSave = (req: SearchRequest): Promise<SearchResponse> =>
  api.post("/jobs/search-and-save", req).then(r => r.data)

export const getJobs = (params?: {
  status?: string
  stage?: string
  q?: string
}): Promise<Job[]> =>
  api.get("/jobs", { params }).then(r => r.data)

export const getJobStats = (): Promise<JobStats> =>
  api.get("/jobs/stats").then(r => r.data)

export const getJob = (id: number): Promise<Job> =>
  api.get(`/jobs/${id}`).then(r => r.data)

export const updateJobStatus = (id: number, status: string) =>
  api.patch(`/jobs/${id}/status`, { status }).then(r => r.data)

export const restoreJob = (id: number) =>
  api.post(`/jobs/${id}/restore`).then(r => r.data)

export const deleteJob = (id: number) =>
  api.delete(`/jobs/${id}`).then(r => r.data)

// ── Per-job tailored resume (Phase 3c) ────────────────────────────────────────

export interface TailoredResumeResponse {
  text: string
  is_tailored: boolean
  source: "tailored" | "master" | "none"
}

export const getTailoredResume = (jobId: number): Promise<TailoredResumeResponse> =>
  api.get(`/jobs/${jobId}/tailored-resume`).then(r => r.data)

export const saveTailoredResume = (jobId: number, text: string) =>
  api.post(`/jobs/${jobId}/tailored-resume`, { text }).then(r => r.data)

export const resetTailoredResume = (jobId: number) =>
  api.delete(`/jobs/${jobId}/tailored-resume`).then(r => r.data)

// ── Apply-intent tracking (did-you-apply modal) ──────────────────────────────
export const recordApplyIntent = (id: number) =>
  api.post(`/jobs/${id}/apply-intent`).then(r => r.data)

export const getPendingApplyIntents = (): Promise<Job[]> =>
  api.get("/jobs/apply-intents/pending").then(r => r.data)

export const acknowledgeApplyIntent = (id: number, applied: boolean) =>
  api.post(`/jobs/${id}/apply-intent/acknowledge`, { applied }).then(r => r.data)

// ── Database management ─────────────────────────────────────────────────────
export const clearAllData = (req: ClearDataRequest): Promise<ClearDataResponse> =>
  api.post("/database/clear", req).then(r => r.data)

// ── ATS ────────────────────────────────────────────────────────────────────────
export const runATSScan = (params: {
  resume_text: string
  job_description: string
  job_id?: number
}): Promise<ATSScanResult> =>
  api.post("/ats/scan", params).then(r => r.data)

// ── Resume ─────────────────────────────────────────────────────────────────────
export const uploadResume = (file: File): Promise<{
  filename: string
  text_length: number
  skills: string[]
  name?: string
  email?: string
  phone?: string
}> => {
  const formData = new FormData()
  formData.append("file", file)
  return api.post("/resume/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then(r => r.data)
}

export const getResume = (): Promise<Resume | null> =>
  api.get("/resume").then(r => r.data)

export const getResumeExperience = (): Promise<ExperienceInfo> =>
  api.get("/resume/experience").then(r => r.data)

// ── Profile ────────────────────────────────────────────────────────────────────
export const getProfile = (): Promise<Record<string, string>> =>
  api.get("/profile").then(r => r.data)

export const updateProfile = (data: {
  candidate_name?: string
  candidate_email?: string
  default_threshold?: number
}) => api.patch("/profile", data).then(r => r.data)
