"use client"

import { useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { runATSScan, getJobs, getResume } from "@/lib/api"
import type { ATSScanResult, ATSSuggestion, BulletRewrite } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  ScanText, Loader2, CheckCircle2, XCircle,
  AlertCircle, TrendingUp, Zap, BookOpen, Copy, Check,
  ArrowRight, Sparkles,
} from "lucide-react"
import { cn } from "@/lib/utils"

const PRIORITY_CONFIG = {
  high:   { color: "border-red-400 bg-red-50",            badge: "bg-red-100 text-red-700",          icon: AlertCircle  },
  medium: { color: "border-amber-400 bg-amber-50",         badge: "bg-amber-100 text-amber-700",       icon: TrendingUp   },
  low:    { color: "border-emerald-400 bg-emerald-50",     badge: "bg-emerald-100 text-emerald-700",   icon: CheckCircle2 },
}

export default function ATSPage() {
  const [mode, setMode]           = useState<"job" | "manual">("job")
  const [selectedJobId, setJobId] = useState<string>("")
  const [manualJD, setManualJD]   = useState("")
  const [result, setResult]       = useState<ATSScanResult | null>(null)

  const { data: resume } = useQuery({
    queryKey: ["resume"],
    queryFn: getResume,
    staleTime: 5 * 60_000,
  })
  const { data: jobs = [] } = useQuery({
    queryKey: ["jobs", "shortlisted"],
    queryFn: () => getJobs({ status: "shortlisted" }),
    staleTime: 60_000,
  })

  const scan = useMutation({
    mutationFn: runATSScan,
    onSuccess: (data) => setResult(data),
  })

  const selectedJob = jobs.find(j => j.id === Number(selectedJobId))
  const jd = mode === "job" ? (selectedJob?.description_full || selectedJob?.description || "") : manualJD

  const handleScan = () => {
    if (!resume?.text || !jd.trim()) return
    scan.mutate({ resume_text: resume.text, job_description: jd, job_id: selectedJob?.id })
  }

  if (!resume) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-400">
        <BookOpen className="w-12 h-12 mb-4" />
        <p className="font-medium text-slate-600">No resume uploaded yet</p>
        <p className="text-sm mt-1">
          <a href="/resume" className="text-blue-600 hover:underline">Upload your resume</a> to use the ATS scanner
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">ATS Scanner</h1>
        <p className="text-slate-500 text-sm mt-1">
          AI-powered resume analysis — see exactly which keywords you&apos;re missing and how to fix them.
        </p>
      </div>

      {/* Source selection */}
      <Card>
        <CardContent className="pt-5 space-y-4">
          <div className="flex gap-4">
            <button
              onClick={() => setMode("job")}
              className={cn(
                "flex-1 p-3 rounded-lg border-2 text-sm font-medium transition-all text-left",
                mode === "job"
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-slate-200 text-slate-500 hover:border-slate-300"
              )}
            >
              <div className="font-semibold">Select from saved jobs</div>
              <div className="text-xs opacity-70 mt-0.5">Use a job already in your pipeline</div>
            </button>
            <button
              onClick={() => setMode("manual")}
              className={cn(
                "flex-1 p-3 rounded-lg border-2 text-sm font-medium transition-all text-left",
                mode === "manual"
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-slate-200 text-slate-500 hover:border-slate-300"
              )}
            >
              <div className="font-semibold">Paste job description</div>
              <div className="text-xs opacity-70 mt-0.5">Copy from any job site</div>
            </button>
          </div>

          {mode === "job" ? (
            // Trigger is full-width; SelectContent inherits that width via
            // CSS `--anchor-width`, so long job titles don't get truncated
            // in the dropdown. SelectItem keeps `whitespace-normal` so very
            // long "Title @ Company" strings can wrap to two lines instead
            // of being clipped.
            <Select value={selectedJobId} onValueChange={v => setJobId(v ?? "")}>
              <SelectTrigger className="w-full min-h-10">
                <SelectValue placeholder="Choose a job to scan against..." />
              </SelectTrigger>
              <SelectContent className="max-w-[640px]">
                {jobs.map(j => (
                  <SelectItem
                    key={j.id}
                    value={String(j.id)}
                    className="whitespace-normal py-2"
                  >
                    <span className="flex flex-col gap-0.5">
                      <span className="font-medium text-slate-900 leading-snug">{j.title}</span>
                      <span className="text-xs text-slate-500">
                        {j.company}
                        {j.location ? ` · ${j.location}` : ""}
                        {" — "}
                        {j.match_score.toFixed(0)}% match
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Textarea
              placeholder="Paste the full job description here..."
              value={manualJD}
              onChange={e => setManualJD(e.target.value)}
              rows={6}
              className="resize-none text-sm"
            />
          )}

          <Button
            onClick={handleScan}
            disabled={!jd.trim() || scan.isPending}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white"
          >
            {scan.isPending ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Analyzing…</>
            ) : (
              <><ScanText className="w-4 h-4 mr-2" />Run ATS Scan</>
            )}
          </Button>
        </CardContent>
      </Card>

      {result && <ATSResults result={result} />}
    </div>
  )
}

// ─── Results panel ────────────────────────────────────────────────────────────

function ATSResults({ result }: { result: ATSScanResult }) {
  const { ats_score, keyword_score, semantic_score, found_keywords,
    missing_keywords, missing_by_section, suggestions,
    bullet_rewrites = [] } = result

  const scoreColor     = ats_score >= 75 ? "text-emerald-600" : ats_score >= 50 ? "text-amber-600" : "text-red-500"
  const scoreLabel     = ats_score >= 75 ? "Strong Match"     : ats_score >= 50 ? "Moderate Match" : "Needs Work"
  const scoreRingColor = ats_score >= 75 ? "#10b981"           : ats_score >= 50 ? "#f59e0b"        : "#ef4444"

  return (
    <div className="space-y-5">
      {/* Score card */}
      <Card>
        <CardContent className="pt-6 pb-5">
          <div className="flex items-center gap-8">
            <div className="relative w-28 h-28 shrink-0">
              <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="#e2e8f0" strokeWidth="10" />
                <circle
                  cx="50" cy="50" r="42"
                  fill="none"
                  stroke={scoreRingColor}
                  strokeWidth="10"
                  strokeDasharray={`${2 * Math.PI * 42}`}
                  strokeDashoffset={`${2 * Math.PI * 42 * (1 - ats_score / 100)}`}
                  strokeLinecap="round"
                  className="transition-all duration-700"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={cn("text-2xl font-bold", scoreColor)}>{ats_score.toFixed(0)}%</span>
                <span className="text-[10px] text-slate-400 font-medium">ATS Score</span>
              </div>
            </div>

            <div className="flex-1 space-y-3">
              <div>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-slate-600 font-medium">Keyword Match</span>
                  <span className="font-bold text-slate-800">{keyword_score.toFixed(0)}%</span>
                </div>
                <Progress value={keyword_score} className="h-2" />
                <p className="text-xs text-slate-400 mt-1">How many key JD terms appear in your resume (60% weight)</p>
              </div>
              <div>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-slate-600 font-medium">Semantic Match</span>
                  <span className="font-bold text-slate-800">{semantic_score.toFixed(0)}%</span>
                </div>
                <Progress value={semantic_score} className="h-2" />
                <p className="text-xs text-slate-400 mt-1">Overall topic alignment via AI embeddings (40% weight)</p>
              </div>
            </div>

            <div className="text-right shrink-0">
              <div className={cn("text-lg font-bold", scoreColor)}>{scoreLabel}</div>
              <div className="text-xs text-slate-400 mt-1">
                {found_keywords.length} found · {missing_keywords.length} missing
              </div>
              {bullet_rewrites.length > 0 && (
                <div className="text-xs text-purple-600 font-medium mt-1">
                  {bullet_rewrites.length} rewrites ready
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="suggestions">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger value="suggestions">
            Suggestions ({suggestions.length})
          </TabsTrigger>
          <TabsTrigger value="rewrites" className="flex items-center gap-1">
            <Sparkles className="w-3 h-3" />
            Rewrites ({bullet_rewrites.length})
          </TabsTrigger>
          <TabsTrigger value="keywords">Keywords</TabsTrigger>
          <TabsTrigger value="sections">By Section</TabsTrigger>
        </TabsList>

        {/* Suggestions tab */}
        <TabsContent value="suggestions" className="mt-4 space-y-3">
          {suggestions.length === 0 ? (
            <div className="text-center py-8 text-emerald-600">
              <CheckCircle2 className="w-10 h-10 mx-auto mb-2" />
              <p className="font-medium">Excellent match — no major improvements needed!</p>
            </div>
          ) : (
            suggestions.map((s, i) => <SuggestionCard key={i} suggestion={s} />)
          )}
        </TabsContent>

        {/* Rewrites tab */}
        <TabsContent value="rewrites" className="mt-4 space-y-3">
          {bullet_rewrites.length === 0 ? (
            <div className="text-center py-10 text-slate-400">
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p className="font-medium text-slate-500">No rewrite suggestions</p>
              <p className="text-sm mt-1">
                This appears when missing keywords can be semantically matched<br />
                to existing bullets in your resume.
              </p>
            </div>
          ) : (
            <>
              <div className="flex items-start gap-3 p-3 bg-purple-50 border border-purple-200 rounded-xl text-sm text-purple-800">
                <Sparkles className="w-4 h-4 mt-0.5 shrink-0 text-purple-500" />
                <span>
                  These suggestions show how to <strong>incorporate missing keywords</strong> directly
                  into your existing bullet points. The AI found which bullet is most relevant
                  to each keyword and generated a natural rewrite. Copy the improved version to your resume.
                </span>
              </div>
              {bullet_rewrites.map((r, i) => <RewriteCard key={i} rewrite={r} />)}
            </>
          )}
        </TabsContent>

        {/* Keywords tab */}
        <TabsContent value="keywords" className="mt-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2 text-emerald-700">
                  <CheckCircle2 className="w-4 h-4" />
                  Found in your resume ({found_keywords.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {found_keywords.map(kw => (
                    <span key={kw} className="px-2.5 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full text-xs font-medium">
                      {kw}
                    </span>
                  ))}
                  {found_keywords.length === 0 && <p className="text-slate-400 text-sm">None found yet</p>}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2 text-red-600">
                  <XCircle className="w-4 h-4" />
                  Missing from your resume ({missing_keywords.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {missing_keywords.slice(0, 40).map(kw => (
                    <span key={kw} className="px-2.5 py-1 bg-red-50 text-red-600 border border-red-200 rounded-full text-xs font-medium">
                      {kw}
                    </span>
                  ))}
                  {missing_keywords.length > 40 && (
                    <span className="text-slate-400 text-xs self-center">+{missing_keywords.length - 40} more</span>
                  )}
                  {missing_keywords.length === 0 && (
                    <p className="text-emerald-600 text-sm font-medium">🎉 No missing keywords!</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* By section tab */}
        <TabsContent value="sections" className="mt-4 space-y-3">
          {Object.keys(missing_by_section).length === 0 ? (
            <div className="text-center py-8 text-emerald-600">
              <CheckCircle2 className="w-10 h-10 mx-auto mb-2" />
              <p className="font-medium">No section-level gaps found!</p>
            </div>
          ) : (
            Object.entries(missing_by_section)
              .sort(([, a], [, b]) => b.length - a.length)
              .map(([section, kws]) => (
                <Card key={section}>
                  <CardContent className="pt-4 pb-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-semibold text-slate-800 text-sm capitalize">{section} Section</span>
                      <span className={cn(
                        "px-2 py-0.5 rounded-full text-[10px] font-bold",
                        kws.length >= 4 ? "bg-red-100 text-red-700" :
                        kws.length >= 2 ? "bg-amber-100 text-amber-700" :
                        "bg-slate-100 text-slate-500"
                      )}>
                        {kws.length} missing
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {kws.map(kw => (
                        <span key={kw} className="px-2 py-1 bg-slate-100 text-slate-600 rounded-lg text-xs font-medium">
                          {kw}
                        </span>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ─── Suggestion card ──────────────────────────────────────────────────────────

function SuggestionCard({ suggestion: s }: { suggestion: ATSSuggestion }) {
  const config = PRIORITY_CONFIG[s.priority] || PRIORITY_CONFIG.low
  const Icon = config.icon

  return (
    <div className={cn("border-l-4 p-4 rounded-r-xl", config.color)}>
      <div className="flex items-center gap-2 mb-1.5">
        <Icon className="w-4 h-4" />
        <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full", config.badge)}>
          {s.priority.toUpperCase()}
        </span>
        {s.section && s.section !== "Overall" && (
          <span className="text-xs px-2 py-0.5 bg-white/80 border border-current/20 rounded-full font-medium">
            → {s.section}
          </span>
        )}
        <span className="text-xs text-slate-500 font-medium">{s.category}</span>
      </div>
      <p className="text-sm text-slate-700 leading-relaxed">
        {s.suggestion.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
          part.startsWith("**") ? (
            <strong key={i}>{part.slice(2, -2)}</strong>
          ) : (
            <span key={i}>{part}</span>
          )
        )}
      </p>
    </div>
  )
}

// ─── Rewrite card ─────────────────────────────────────────────────────────────

function RewriteCard({ rewrite: r }: { rewrite: BulletRewrite }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(r.rewrite).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // Confidence label
  const confidence = r.score >= 0.55 ? { label: "High confidence", cls: "bg-emerald-100 text-emerald-700" }
                   : r.score >= 0.38 ? { label: "Good match",      cls: "bg-blue-100 text-blue-700"      }
                   :                   { label: "Possible match",   cls: "bg-slate-100 text-slate-600"    }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 bg-purple-100 text-purple-700 rounded-full text-xs font-bold tracking-wide">
            + {r.keyword}
          </span>
          <span className="text-[11px] text-slate-400 capitalize">
            {r.section} bullet
          </span>
          <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-medium", confidence.cls)}>
            {confidence.label}
          </span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 transition-colors px-2 py-1 rounded hover:bg-slate-100"
        >
          {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>

      {/* Original bullet */}
      <div className="px-4 pt-3 pb-1">
        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Current</div>
        <p className="text-sm text-slate-500 leading-relaxed line-through decoration-slate-300">
          {r.original}
        </p>
      </div>

      {/* Arrow */}
      <div className="flex items-center px-4 py-1 gap-2">
        <div className="h-px flex-1 bg-slate-100" />
        <ArrowRight className="w-4 h-4 text-purple-400 shrink-0" />
        <div className="h-px flex-1 bg-slate-100" />
      </div>

      {/* Rewrite */}
      <div className="px-4 pb-4 pt-1">
        <div className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wider mb-1">Suggested rewrite</div>
        <p className="text-sm leading-relaxed font-medium">
          {/* Render original part in normal slate, added_text in green */}
          <span className="text-slate-700">
            {r.rewrite.slice(0, r.rewrite.length - r.added_text.length - 2).trimEnd()}
          </span>
          <span className="text-emerald-600 font-semibold">
            {", "}
            {r.added_text.replace(/\.$/, "")}.
          </span>
        </p>
      </div>
    </div>
  )
}
