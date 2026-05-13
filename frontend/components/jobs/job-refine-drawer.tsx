"use client"

import { Dialog } from "@base-ui/react/dialog"
import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  X, Sparkles, Loader2, CheckCircle2, AlertCircle, Copy, RotateCcw,
  ExternalLink, ScanText, Save, FileText, FileEdit,
} from "lucide-react"

import {
  runATSScan, recordApplyIntent,
  getTailoredResume, saveTailoredResume, resetTailoredResume,
} from "@/lib/api"
import type { Job, ATSScanResult, ATSSuggestion, BulletRewrite, SummaryRewrite } from "@/lib/types"
import { cn } from "@/lib/utils"

const ATS_PASS_THRESHOLD = 80

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  job: Job
  /** The master resume text — used as fallback when no tailored version saved yet. */
  masterResumeText?: string
}

/**
 * Per-job refine drawer.
 *
 * One-stop panel where the user iterates on their resume content for a
 * specific job: see ATS score, get keyword gaps and LLM-generated bullet
 * rewrites, edit the text in place, re-score until ≥ 80%, then click Apply.
 *
 * Design choice (per user): the master PDF is what's actually uploaded by
 * the extension. The edits here improve the ATS score signal and surface
 * concrete keyword/sentence changes; when the user is satisfied they copy
 * the changes into their master resume in their preferred editor (Word,
 * Docs, Canva) and re-upload via the Resume page. This preserves their
 * professional formatting instead of generating a plain ReportLab PDF.
 */
export function JobRefineDrawer({ open, onOpenChange, job, masterResumeText }: Props) {
  const qc = useQueryClient()

  // Load tailored text (or master) for this job whenever drawer opens.
  const { data: tailoredData } = useQuery({
    queryKey: ["tailored-resume", job.id],
    queryFn:  () => getTailoredResume(job.id),
    enabled:  open,
  })

  const [editorText, setEditorText] = useState("")
  const [scanResult, setScanResult] = useState<ATSScanResult | null>(null)

  // Sync editor when the drawer opens or the loaded tailored text changes
  useEffect(() => {
    if (open && tailoredData) {
      setEditorText(tailoredData.text || masterResumeText || "")
    }
  }, [open, tailoredData, masterResumeText])

  const scanMutation = useMutation({
    mutationFn: () => runATSScan({
      resume_text:     editorText,
      job_description: job.description_full || job.description,
      job_id:          job.id,
    }),
    onSuccess: (data) => {
      setScanResult(data)
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const saveMutation = useMutation({
    mutationFn: () => saveTailoredResume(job.id, editorText),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tailored-resume", job.id] }),
  })

  const resetMutation = useMutation({
    mutationFn: () => resetTailoredResume(job.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tailored-resume", job.id] })
      setEditorText(masterResumeText || "")
      setScanResult(null)
    },
  })

  const handleApplyClick = async () => {
    try {
      await recordApplyIntent(job.id)
      qc.invalidateQueries({ queryKey: ["apply-intents", "pending"] })
    } catch { /* don't block apply on intent failure */ }
    window.open(job.link, "_blank", "noopener,noreferrer")
  }

  const score      = scanResult?.ats_score ?? job.ats_score ?? null
  const passed     = score !== null && score >= ATS_PASS_THRESHOLD
  const isTailored = tailoredData?.is_tailored ?? false
  const dirty      = (tailoredData?.text ?? masterResumeText ?? "") !== editorText

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop
          className={cn(
            "fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40",
            "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
            "transition-opacity duration-200",
          )}
        />
        <Dialog.Popup
          className={cn(
            "fixed right-0 top-0 bottom-0 w-[640px] max-w-[100vw]",
            "bg-white shadow-2xl z-50 flex flex-col",
            "data-[starting-style]:translate-x-full data-[ending-style]:translate-x-full",
            "transition-transform duration-300 ease-out",
          )}
        >
          {/* ── Header ─────────────────────────────────────────────────────── */}
          <div className="flex items-start justify-between p-5 border-b border-slate-100">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-lg font-bold text-slate-900 truncate">
                {job.title}
              </Dialog.Title>
              <Dialog.Description className="text-sm text-slate-500 mt-0.5 truncate">
                {job.company} {job.location ? `· ${job.location}` : ""}
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="ml-3 p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </Dialog.Close>
          </div>

          {/* ── Body (scrollable) ──────────────────────────────────────────── */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">

            {/* Score card */}
            <ScoreCard
              score={score}
              passed={passed}
              isTailored={isTailored}
              isLoading={scanMutation.isPending}
              onScan={() => scanMutation.mutate()}
              kw={scanResult?.keyword_score ?? null}
              sem={scanResult?.semantic_score ?? null}
            />

            {/* Missing & implied keywords */}
            {scanResult && (
              <KeywordSection
                missing={scanResult.missing_keywords}
                implied={scanResult.implied_keywords ?? []}
                found={scanResult.found_keywords}
              />
            )}

            {/* LLM-generated summary rewrite (when produced) */}
            {scanResult && scanResult.summary_rewrite && (
              <SummaryRewriteSection rewrite={scanResult.summary_rewrite} />
            )}

            {/* LLM-generated bullet rewrites */}
            {scanResult && scanResult.bullet_rewrites.length > 0 && (
              <BulletRewriteSection rewrites={scanResult.bullet_rewrites} />
            )}

            {/* Section-level suggestions */}
            {scanResult && scanResult.suggestions.length > 0 && (
              <SuggestionSection suggestions={scanResult.suggestions} />
            )}

            {/* Editor */}
            <ResumeEditor
              text={editorText}
              onChange={setEditorText}
              isTailored={isTailored}
              dirty={dirty}
              onSave={() => saveMutation.mutate()}
              onReset={() => resetMutation.mutate()}
              isSaving={saveMutation.isPending}
              isResetting={resetMutation.isPending}
            />
          </div>

          {/* ── Footer ─────────────────────────────────────────────────────── */}
          <div className="p-4 border-t border-slate-100 flex items-center justify-between gap-2 bg-slate-50">
            <div className="text-xs text-slate-500">
              {passed ? (
                <span className="text-emerald-700 font-medium flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Ready to apply
                </span>
              ) : score !== null ? (
                <span className="text-amber-700">
                  Need {ATS_PASS_THRESHOLD}% to flag as ATS-ready
                </span>
              ) : (
                <span>Run an ATS scan to see your score</span>
              )}
            </div>

            <button
              onClick={handleApplyClick}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold",
                passed
                  ? "bg-emerald-600 text-white hover:bg-emerald-700"
                  : "bg-blue-600 text-white hover:bg-blue-700",
              )}
            >
              <ExternalLink className="w-4 h-4" />
              Apply with master resume
            </button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ScoreCard({
  score, passed, isTailored, isLoading, onScan, kw, sem,
}: {
  score: number | null
  passed: boolean
  isTailored: boolean
  isLoading: boolean
  onScan: () => void
  kw: number | null
  sem: number | null
}) {
  return (
    <div className={cn(
      "rounded-xl border p-4",
      passed ? "bg-emerald-50 border-emerald-200" :
      score !== null ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-200",
    )}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {score !== null
            ? (passed
                ? <CheckCircle2 className="w-6 h-6 text-emerald-600" />
                : <AlertCircle className="w-6 h-6 text-amber-600" />)
            : <ScanText className="w-6 h-6 text-slate-400" />}
          <div>
            <div className="text-2xl font-bold text-slate-900 leading-none">
              {score !== null ? `${score.toFixed(0)}%` : "—"}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {kw !== null && sem !== null
                ? `Keywords ${kw.toFixed(0)}% · Semantic ${sem.toFixed(0)}%`
                : "ATS score not yet computed"}
            </div>
          </div>
        </div>

        <button
          onClick={onScan}
          disabled={isLoading}
          className={cn(
            "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border",
            "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50",
          )}
        >
          {isLoading
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Scanning…</>
            : <><Sparkles className="w-4 h-4" /> {score !== null ? "Re-check ATS" : "Check ATS"}</>}
        </button>
      </div>
      {isTailored && (
        <p className="mt-3 text-[11px] text-slate-500">
          Showing the tailored draft you saved for this job.
        </p>
      )}
    </div>
  )
}


function KeywordSection({
  missing, implied, found,
}: { missing: string[]; implied: string[]; found: string[] }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-slate-800 text-sm">Keyword coverage</h4>
        <span className="text-[11px] text-slate-500">
          {found.length} found · {implied.length} implied · {missing.length} missing
        </span>
      </div>

      {missing.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Missing — add these to your resume
          </p>
          <div className="flex flex-wrap gap-1.5">
            {missing.map(kw => (
              <span key={kw} className="px-2 py-0.5 bg-red-50 text-red-700 border border-red-200 rounded-full text-[11px] font-medium">
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {implied.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Implied — covered semantically (no exact match)
          </p>
          <div className="flex flex-wrap gap-1.5">
            {implied.map(kw => (
              <span key={kw} className="px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded-full text-[11px] font-medium">
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


function SummaryRewriteSection({ rewrite }: { rewrite: SummaryRewrite }) {
  const [copied, setCopied] = useState(false)

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(rewrite.rewrite)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-slate-800 text-sm flex items-center gap-1.5">
          <FileEdit className="w-4 h-4 text-blue-600" />
          {rewrite.is_new ? "Suggested new Professional Summary" : "Tailored Professional Summary"}
        </h4>
        <button
          onClick={onCopy}
          className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
        >
          {copied ? <CheckCircle2 className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {rewrite.is_new ? (
        <p className="text-[11px] text-slate-500">
          Your resume has no Summary section. This is a tailored 2-3 sentence
          summary you can paste at the top.
        </p>
      ) : (
        <p className="text-[11px] text-slate-500">
          Your current summary, tailored to this job&apos;s language while
          staying grounded in your actual experience.
        </p>
      )}

      {!rewrite.is_new && rewrite.original && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-0.5">Current</p>
          <p className="text-xs text-slate-600">{rewrite.original}</p>
        </div>
      )}
      <div>
        <p className="text-[10px] font-semibold text-blue-600 uppercase tracking-wider mb-0.5">
          Tailored
        </p>
        <p className="text-xs text-slate-800 font-medium leading-relaxed">{rewrite.rewrite}</p>
      </div>
    </div>
  )
}


function BulletRewriteSection({ rewrites }: { rewrites: BulletRewrite[] }) {
  const [copied, setCopied] = useState<string | null>(null)

  const onCopy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied(null), 1500)
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-3">
      <h4 className="font-semibold text-slate-800 text-sm flex items-center gap-1.5">
        <Sparkles className="w-4 h-4 text-purple-500" />
        Suggested bullet rewrites
      </h4>
      <p className="text-[11px] text-slate-500">
        Copy a rewrite and paste it into your master resume in your editor.
        Then re-upload from the Resume page when satisfied.
      </p>
      <div className="space-y-3">
        {rewrites.map((rw, i) => {
          const key = `rw-${i}`
          return (
            <div key={key} className="rounded-lg border border-slate-100 bg-slate-50 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold text-purple-700 uppercase tracking-wider">
                  + {rw.keyword}
                </span>
                <div className="flex items-center gap-2">
                  {rw.engine && (
                    <span className={cn(
                      "text-[9px] px-1.5 py-0.5 rounded font-semibold uppercase tracking-wider",
                      rw.engine === "llm"
                        ? "bg-purple-100 text-purple-700"
                        : "bg-slate-200 text-slate-600",
                    )}>
                      {rw.engine === "llm" ? "AI" : "Template"}
                    </span>
                  )}
                  <button
                    onClick={() => onCopy(rw.rewrite, key)}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
                  >
                    {copied === key ? <CheckCircle2 className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {copied === key ? "Copied" : "Copy"}
                  </button>
                </div>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-0.5">Before</p>
                <p className="text-xs text-slate-600 line-through decoration-slate-300">{rw.original}</p>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wider mb-0.5">After</p>
                <p className="text-xs text-slate-800 font-medium">{rw.rewrite}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}


function SuggestionSection({ suggestions }: { suggestions: ATSSuggestion[] }) {
  const PRIORITY_STYLES: Record<string, string> = {
    high:   "bg-red-50 border-red-200 text-red-700",
    medium: "bg-amber-50 border-amber-200 text-amber-700",
    low:    "bg-blue-50 border-blue-200 text-blue-700",
  }
  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-3">
      <h4 className="font-semibold text-slate-800 text-sm">Section suggestions</h4>
      <div className="space-y-2">
        {suggestions.map((s, i) => (
          <div
            key={i}
            className={cn(
              "rounded-lg border p-3 text-xs",
              PRIORITY_STYLES[s.priority] ?? "bg-slate-50 border-slate-200 text-slate-700",
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[9px] font-bold uppercase tracking-wider opacity-80">
                {s.priority}
              </span>
              <span className="text-[10px] font-semibold">{s.section} · {s.category}</span>
            </div>
            <div
              className="leading-relaxed [&_code]:bg-white [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[10px] [&_strong]:font-semibold"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(s.suggestion) }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}


function ResumeEditor({
  text, onChange, isTailored, dirty, onSave, onReset, isSaving, isResetting,
}: {
  text: string
  onChange: (s: string) => void
  isTailored: boolean
  dirty: boolean
  onSave: () => void
  onReset: () => void
  isSaving: boolean
  isResetting: boolean
}) {
  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-slate-800 text-sm flex items-center gap-1.5">
          <FileText className="w-4 h-4 text-slate-500" />
          Resume text editor
        </h4>
        <div className="flex items-center gap-2">
          {isTailored && (
            <button
              onClick={onReset}
              disabled={isResetting}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 disabled:opacity-50"
              title="Discard tailored version, use master resume"
            >
              <RotateCcw className="w-3 h-3" />
              {isResetting ? "Resetting…" : "Reset to master"}
            </button>
          )}
          <button
            onClick={onSave}
            disabled={isSaving || !dirty}
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border",
              dirty
                ? "bg-blue-600 text-white border-blue-600 hover:bg-blue-700"
                : "bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed",
            )}
          >
            {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            Save tailored
          </button>
        </div>
      </div>
      <p className="text-[11px] text-slate-500">
        Edit here to test ATS-keyword changes. The extension still uploads your master PDF — when you find changes you want to keep, copy them into your resume editor (Word, Docs, Canva), then re-upload from the Resume page.
      </p>
      <textarea
        value={text}
        onChange={e => onChange(e.target.value)}
        rows={14}
        className="w-full rounded-lg border border-slate-200 p-3 text-xs font-mono leading-relaxed focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-y"
        spellCheck={false}
      />
    </div>
  )
}


/** Tiny markdown renderer for the suggestion strings (bold + inline code). */
function renderMarkdown(s: string): string {
  return s
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
}
