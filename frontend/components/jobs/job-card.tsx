"use client"

import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import {
  ExternalLink, MapPin, Calendar, DollarSign,
  ChevronDown, ChevronUp, ScanText, Loader2,
  CheckCircle2, XCircle, AlertCircle, Sparkles, Trash2,
} from "lucide-react"
import type { Job, ATSScanResult } from "@/lib/types"
import { runATSScan, deleteJob, recordApplyIntent } from "@/lib/api"
import { cn } from "@/lib/utils"
import { useQueryClient } from "@tanstack/react-query"
import { JobRefineDrawer } from "./job-refine-drawer"

// ── Constants ─────────────────────────────────────────────────────────────────

const SOURCE_COLORS: Record<string, string> = {
  JSearch: "#4285f4", Adzuna: "#0066cc", "The Muse": "#e91e8c",
  Arbeitnow: "#6f42c1", RemoteOK: "#17a2b8", Remotive: "#20c997",
  Jobicy: "#fd7e14", Himalayas: "#7c3aed", USAJobs: "#0ea5e9",
  Findwork: "#e83e8c", Jooble: "#28a745",
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  shortlisted:   { label: "Saved",        color: "bg-blue-100 text-blue-700"       },
  applied_email: { label: "Applied",      color: "bg-emerald-100 text-emerald-700" },
  applied_link:  { label: "Applied",      color: "bg-emerald-100 text-emerald-700" },
  following_up:  { label: "Following Up", color: "bg-amber-100 text-amber-700"     },
  interview:     { label: "Interview",    color: "bg-purple-100 text-purple-700"   },
  offer:         { label: "Offer!",       color: "bg-emerald-100 text-emerald-700" },
  skipped:       { label: "Skipped",      color: "bg-slate-100 text-slate-500"     },
}

const ATS_PASS_THRESHOLD = 80

// ── Types ─────────────────────────────────────────────────────────────────────

interface JobCardProps {
  job: Job
  compact?: boolean
  resumeText?: string          // required for inline ATS check
  onStatusChange?: (id: number, status: string) => void
  onDelete?: (id: number) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export function JobCard({ job, compact = false, resumeText, onStatusChange, onDelete }: JobCardProps) {
  const qc = useQueryClient()
  const [expanded, setExpanded]   = useState(false)
  const [atsResult, setAtsResult] = useState<ATSScanResult | null>(null)
  const [showAts, setShowAts]     = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [refineOpen, setRefineOpen] = useState(false)

  /**
   * Apply click handler: records the apply-intent in the backend BEFORE
   * opening the external job URL in a new tab. The dashboard's
   * DidYouApplyModal then asks "Did you apply?" when the user returns.
   *
   * We use window.open here (not a plain <a target="_blank">) so we can run
   * the intent POST first; the small delay is unnoticeable but ensures the
   * intent is recorded even if the user closes the source tab quickly.
   */
  const handleApplyClick = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault()
    try {
      await recordApplyIntent(job.id)
      qc.invalidateQueries({ queryKey: ["apply-intents", "pending"] })
    } catch {
      // If the intent POST fails the user can still apply — don't block them.
    }
    window.open(job.link, "_blank", "noopener,noreferrer")
  }

  const sourceColor = SOURCE_COLORS[job.source] || "#666"
  const statusMeta  = STATUS_META[job.status] || { label: job.status, color: "bg-slate-100 text-slate-600" }

  const matchScoreColor = job.match_score >= 85
    ? "text-emerald-600 bg-emerald-50"
    : job.match_score >= 65
    ? "text-amber-600 bg-amber-50"
    : "text-red-500 bg-red-50"

  const atsMutation = useMutation({
    mutationFn: () => runATSScan({
      resume_text: resumeText || "",
      job_description: job.description_full || job.description,
      job_id: job.id,
    }),
    onSuccess: (data) => {
      setAtsResult(data)
      setShowAts(true)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteJob(job.id),
    onSuccess: () => onDelete?.(job.id),
  })

  const handleCheckAts = () => {
    if (!resumeText) return
    if (atsResult) {
      setShowAts(v => !v)
      return
    }
    atsMutation.mutate()
  }

  const atsScore     = atsResult?.ats_score ?? job.ats_score ?? null
  const atsReady     = atsScore !== null && atsScore >= ATS_PASS_THRESHOLD
  const atsChecked   = atsScore !== null
  const canCheckAts  = !!resumeText && !compact

  return (
    <div className={cn(
      "bg-white rounded-xl border shadow-sm hover:shadow-md transition-shadow",
      atsReady ? "border-emerald-300" : "border-slate-200"
    )}>
      {/* ATS-friendly banner */}
      {atsReady && (
        <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 border-b border-emerald-200 rounded-t-xl text-xs text-emerald-700 font-medium">
          <CheckCircle2 className="w-3.5 h-3.5" />
          ATS Friendly — This resume scores {atsScore?.toFixed(0)}% against this job. Safe to apply!
        </div>
      )}

      <div className="p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-2 flex-wrap">
              <h3 className="font-semibold text-slate-900 text-sm leading-tight">{job.title}</h3>
              {job.remote && (
                <span className="px-2 py-0.5 bg-cyan-50 text-cyan-700 rounded-full text-[10px] font-medium border border-cyan-200 shrink-0">
                  Remote
                </span>
              )}
              {job.h1b_mention && (
                <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded-full text-[10px] font-medium border border-emerald-200 shrink-0">
                  H1B
                </span>
              )}
            </div>
            <p className="text-slate-500 text-xs mt-0.5">{job.company}</p>
          </div>

          {/* Score + source */}
          <div className="flex items-center gap-2 shrink-0">
            <span className={cn("px-2.5 py-1 rounded-full text-xs font-bold", matchScoreColor)}>
              {job.match_score.toFixed(0)}%
            </span>
            <span
              className="px-2 py-1 rounded-full text-[10px] font-semibold text-white"
              style={{ backgroundColor: sourceColor }}
            >
              {job.source}
            </span>
          </div>
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-slate-400">
          {job.location && (
            <span className="flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              {job.location}
            </span>
          )}
          {job.date_posted && (
            <span className="flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              {job.date_posted}
            </span>
          )}
          {job.salary_text && (
            <span className="flex items-center gap-1 text-emerald-600 font-medium">
              <DollarSign className="w-3 h-3" />
              {job.salary_text}
            </span>
          )}
          {atsChecked && !atsReady && (
            <span className={cn(
              "px-2 py-0.5 rounded-full text-[10px] font-bold",
              atsScore! >= 60 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-600"
            )}>
              ATS {atsScore?.toFixed(0)}%
            </span>
          )}
          <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium", statusMeta.color)}>
            {statusMeta.label}
          </span>
        </div>

        {/* Description (expandable) */}
        {!compact && job.description && (
          <div className="mt-3">
            <p className={cn("text-xs text-slate-600 leading-relaxed", !expanded && "line-clamp-2")}>
              {job.description}
            </p>
            {job.description.length > 120 && (
              <button
                onClick={() => setExpanded(v => !v)}
                className="flex items-center gap-1 text-blue-600 text-xs mt-1 hover:underline"
              >
                {expanded
                  ? <><ChevronUp className="w-3 h-3" />Show less</>
                  : <><ChevronDown className="w-3 h-3" />Show more</>}
              </button>
            )}
          </div>
        )}

        {/* Inline ATS result panel */}
        {showAts && atsResult && (
          <ATSInlinePanel result={atsResult} jobId={job.id} />
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-100 flex-wrap">
          <a
            href={job.link}
            onClick={handleApplyClick}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              atsReady
                ? "bg-emerald-600 text-white hover:bg-emerald-700"
                : "bg-blue-600 text-white hover:bg-blue-700"
            )}
          >
            <ExternalLink className="w-3 h-3" />
            Apply
          </a>

          {/* Inline ATS check button — only shown when resume is available */}
          {canCheckAts && (
            <button
              onClick={handleCheckAts}
              disabled={atsMutation.isPending}
              title={!resumeText ? "Upload a resume first to check ATS score" : ""}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                atsReady
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                  : atsChecked
                  ? "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
                  : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              )}
            >
              {atsMutation.isPending ? (
                <><Loader2 className="w-3 h-3 animate-spin" />Scanning…</>
              ) : atsReady ? (
                <><CheckCircle2 className="w-3 h-3" />ATS Ready</>
              ) : atsChecked ? (
                <><AlertCircle className="w-3 h-3" />ATS {atsScore?.toFixed(0)}% — see fixes</>
              ) : (
                <><ScanText className="w-3 h-3" />Check ATS</>
              )}
            </button>
          )}

          {/* Refine drawer — full ATS panel + suggestions + rewrites + editor */}
          {canCheckAts && (
            <button
              onClick={() => setRefineOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100"
            >
              <Sparkles className="w-3 h-3" />
              Refine for this job
            </button>
          )}

          {onStatusChange && (
            <>
              <button
                onClick={() => onStatusChange(job.id, "applied_link")}
                className="px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-xs font-medium hover:bg-emerald-100 transition-colors border border-emerald-200"
              >
                Mark Applied
              </button>
              <button
                onClick={() => onStatusChange(job.id, "following_up")}
                className="px-3 py-1.5 bg-amber-50 text-amber-700 rounded-lg text-xs font-medium hover:bg-amber-100 transition-colors border border-amber-200"
              >
                Following Up
              </button>
              <button
                onClick={() => onStatusChange(job.id, "interview")}
                className="px-3 py-1.5 bg-purple-50 text-purple-700 rounded-lg text-xs font-medium hover:bg-purple-100 transition-colors border border-purple-200"
              >
                Interview
              </button>
              <button
                onClick={() => onStatusChange(job.id, "skipped")}
                className="px-3 py-1.5 text-slate-500 rounded-lg text-xs hover:bg-slate-50 transition-colors"
              >
                Skip
              </button>
            </>
          )}

          {/* Delete */}
          {onDelete && (
            <div className="ml-auto">
              {deleteConfirm ? (
                <div className="flex items-center gap-1">
                  <span className="text-xs text-red-600">Delete?</span>
                  <button
                    onClick={() => deleteMutation.mutate()}
                    className="px-2 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700"
                  >
                    Yes
                  </button>
                  <button
                    onClick={() => setDeleteConfirm(false)}
                    className="px-2 py-1 text-slate-500 text-xs hover:bg-slate-100 rounded"
                  >
                    No
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setDeleteConfirm(true)}
                  className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                  title="Delete this job"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Refine drawer (rendered into a portal — outside the card visually) */}
      <JobRefineDrawer
        open={refineOpen}
        onOpenChange={setRefineOpen}
        job={job}
        masterResumeText={resumeText}
      />
    </div>
  )
}

// ── Inline ATS panel (compact, shown inside the job card) ─────────────────────

function ATSInlinePanel({ result, jobId }: { result: ATSScanResult; jobId: number }) {
  const { ats_score, keyword_score, semantic_score, missing_keywords } = result
  const passed = ats_score >= ATS_PASS_THRESHOLD

  return (
    <div className={cn(
      "mt-3 rounded-xl border p-3 space-y-2",
      passed ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"
    )}>
      {/* Score row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {passed
            ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            : <AlertCircle className="w-4 h-4 text-amber-600" />}
          <span className={cn("text-sm font-bold", passed ? "text-emerald-700" : "text-amber-700")}>
            ATS Score: {ats_score.toFixed(0)}%
          </span>
          <span className={cn(
            "text-xs px-2 py-0.5 rounded-full font-medium",
            passed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
          )}>
            {passed ? "Ready to apply!" : `Need ${ATS_PASS_THRESHOLD}% to apply`}
          </span>
        </div>
        <div className="text-xs text-slate-500">
          KW {keyword_score.toFixed(0)}% · Sem {semantic_score.toFixed(0)}%
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-white rounded-full h-2 overflow-hidden border border-slate-100">
        <div
          className={cn("h-full rounded-full transition-all duration-500",
            passed ? "bg-emerald-500" : ats_score >= 60 ? "bg-amber-400" : "bg-red-400"
          )}
          style={{ width: `${ats_score}%` }}
        />
      </div>

      {/* Missing keywords (compact, max 8) */}
      {!passed && missing_keywords.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Missing keywords
          </p>
          <div className="flex flex-wrap gap-1">
            {missing_keywords.slice(0, 8).map(kw => (
              <span key={kw} className="px-2 py-0.5 bg-white text-red-600 border border-red-200 rounded-full text-[10px] font-medium">
                {kw}
              </span>
            ))}
            {missing_keywords.length > 8 && (
              <span className="text-[10px] text-slate-400 self-center">+{missing_keywords.length - 8} more</span>
            )}
          </div>
        </div>
      )}

      {/* Link to full ATS page */}
      {!passed && (
        <a
          href={`/ats?job_id=${jobId}`}
          className="flex items-center gap-1 text-xs text-blue-600 hover:underline font-medium"
        >
          <Sparkles className="w-3 h-3" />
          See full suggestions and sentence rewrites →
        </a>
      )}
    </div>
  )
}
