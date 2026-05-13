"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Search, Loader2, Zap, Filter, ChevronDown, ChevronUp, Info, GraduationCap } from "lucide-react"
import { getBoards, getResumeExperience, searchAndSave } from "@/lib/api"
import type { BoardInfo, SearchRequest, SearchResponse, Job } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Slider } from "@/components/ui/slider"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { JobCard } from "@/components/jobs/job-card"
import { cn } from "@/lib/utils"

const DATE_FILTERS = [
  { label: "Any time",      value: "" },
  { label: "Last 24 hours", value: "1" },
  { label: "Last 3 days",   value: "3" },
  { label: "Last week",     value: "7" },
  { label: "Last month",    value: "30" },
]

const JOB_TYPES = ["Any", "Full-time", "Part-time", "Contract", "Internship"]

const LEVEL_CONFIG: Record<string, { label: string; color: string; desc: string }> = {
  intern: { label: "Intern",  color: "bg-slate-100 text-slate-600",    desc: "0–1 yr"  },
  entry:  { label: "Entry",   color: "bg-blue-100 text-blue-700",      desc: "2–4 yrs" },
  mid:    { label: "Mid",     color: "bg-amber-100 text-amber-700",    desc: "5–8 yrs" },
  senior: { label: "Senior",  color: "bg-purple-100 text-purple-700",  desc: "9+ yrs"  },
}

export default function SearchPage() {
  const qc = useQueryClient()

  const [keywords, setKeywords]       = useState("")
  const [location, setLocation]       = useState("")
  const [dateFilter, setDateFilter]   = useState("")
  const [jobType, setJobType]         = useState("Any")
  const [numPerBoard, setNumPerBoard] = useState(20)
  const [h1bOnly, setH1bOnly]         = useState(false)
  const [hideOld, setHideOld]         = useState(true)
  const [replaceExisting, setReplace] = useState(true)
  const [selectedBoards, setSelected] = useState<Set<string>>(new Set())
  const [showFilters, setShowFilters] = useState(false)
  const [result, setResult]           = useState<SearchResponse | null>(null)

  const { data: boards = [], isLoading: boardsLoading } = useQuery({
    queryKey: ["boards"],
    queryFn: getBoards,
    staleTime: 5 * 60_000,   // board config rarely changes — cache for 5 min
  })

  const { data: experience } = useQuery({
    queryKey: ["experience"],
    queryFn: getResumeExperience,
    staleTime: 5 * 60_000,
    retry: false,
  })

  const handleBoardToggle = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  const allConfigured = boards.filter(b => b.configured)
  const handleSelectAll = () => setSelected(new Set(allConfigured.map(b => b.name)))

  const search = useMutation({
    mutationFn: (req: SearchRequest) => searchAndSave(req),
    onSuccess: (data) => {
      setResult(data)
      qc.invalidateQueries({ queryKey: ["stats"] })
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const handleSearch = () => {
    if (!keywords.trim()) return
    const boards_to_search = selectedBoards.size > 0
      ? Array.from(selectedBoards)
      : allConfigured.map(b => b.name)

    search.mutate({
      keywords: keywords.trim(),
      location,
      boards: boards_to_search,
      num_per_board: numPerBoard,
      date_filter: dateFilter ? Number(dateFilter) : null,
      job_type: jobType !== "Any" ? jobType : null,
      h1b_only: h1bOnly,
      hide_old: hideOld,
      replace_existing: replaceExisting,
    })
  }

  const tierGroups: Record<number, BoardInfo[]> = {}
  for (const b of boards) {
    tierGroups[b.tier] = tierGroups[b.tier] || []
    tierGroups[b.tier].push(b)
  }

  const tierLabels: Record<number, string> = {
    1: "Tier 1 — Primary (free key)",
    2: "Tier 2 — No key needed",
    3: "Tier 3 — Optional keys",
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Job Search</h1>
        <p className="text-slate-500 text-sm mt-1">
          Search across all boards simultaneously. Every result is AI-ranked against your resume —
          no pre-filtering. You decide what to apply for.
        </p>
      </div>

      {/* Experience info banner */}
      {experience && experience.years > 0 && (
        <div className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-xl text-sm">
          <GraduationCap className="w-4 h-4 text-blue-600 shrink-0" />
          <span className="text-blue-800">
            Resume detected: <strong>{experience.years} years</strong> of experience
            ({experience.method === "explicit" ? "stated directly" : "calculated from work history"}) →
            jobs will be sorted to show{" "}
            <span className={cn(
              "px-2 py-0.5 rounded-full text-xs font-bold",
              LEVEL_CONFIG[experience.level]?.color,
            )}>
              {LEVEL_CONFIG[experience.level]?.label ?? experience.level} level
            </span>
            {" "}roles first
          </span>
        </div>
      )}

      {/* Main search inputs */}
      <Card>
        <CardContent className="pt-5 space-y-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <Label htmlFor="keywords" className="text-sm font-medium mb-1.5 block">
                Job title / keywords
              </Label>
              <Input
                id="keywords"
                placeholder="e.g. Python Developer, Data Engineer, Product Manager"
                value={keywords}
                onChange={e => setKeywords(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                className="h-10"
              />
            </div>
            <div className="flex-1">
              <Label htmlFor="location" className="text-sm font-medium mb-1.5 block">
                Location
              </Label>
              <Input
                id="location"
                placeholder="Austin, TX  ·  New York, NY  ·  Remote"
                value={location}
                onChange={e => setLocation(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                className="h-10"
              />
            </div>
          </div>

          <button
            onClick={() => setShowFilters(v => !v)}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
          >
            <Filter className="w-3.5 h-3.5" />
            Advanced filters
            {showFilters ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {showFilters && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 pt-2 border-t border-slate-100">
              <div>
                <Label className="text-xs font-medium text-slate-600 mb-1.5 block">Date posted</Label>
                <Select value={dateFilter} onValueChange={v => setDateFilter(v ?? "")}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DATE_FILTERS.map(f => (
                      <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-xs font-medium text-slate-600 mb-1.5 block">Job type</Label>
                <Select value={jobType} onValueChange={v => setJobType(v ?? "Any")}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {JOB_TYPES.map(t => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-xs font-medium text-slate-600 mb-1.5 block">
                  Results per board: {numPerBoard}
                </Label>
                <Slider
                  min={5} max={30} step={5}
                  value={[numPerBoard]}
                  onValueChange={(v) => setNumPerBoard(Array.isArray(v) ? v[0] : v)}
                  className="mt-3"
                />
              </div>

              <div className="flex items-center gap-2">
                <Checkbox id="h1b" checked={h1bOnly} onCheckedChange={v => setH1bOnly(!!v)} />
                <Label htmlFor="h1b" className="text-sm cursor-pointer">H1B / Visa sponsorship only</Label>
              </div>

              <div className="flex items-center gap-2">
                <Checkbox id="hideOld" checked={hideOld} onCheckedChange={v => setHideOld(!!v)} />
                <Label htmlFor="hideOld" className="text-sm cursor-pointer">Hide listings older than 30 days</Label>
              </div>

              <div className="flex items-center gap-2">
                <Checkbox id="replace" checked={replaceExisting} onCheckedChange={v => setReplace(!!v)} />
                <Label htmlFor="replace" className="text-sm cursor-pointer">Replace existing shortlist</Label>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Board selector */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Job Boards</CardTitle>
            <button onClick={handleSelectAll} className="text-xs text-blue-600 hover:underline">
              Select all configured
            </button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {boardsLoading ? (
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />Loading boards…
            </div>
          ) : (
            [1, 2, 3].map(tier => {
              const tierBoards = tierGroups[tier] || []
              if (!tierBoards.length) return null
              return (
                <div key={tier}>
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                    {tierLabels[tier]}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {tierBoards.map(board => {
                      const isSelected = selectedBoards.has(board.name) ||
                        (selectedBoards.size === 0 && board.configured)
                      const isDisabled = !board.configured
                      return (
                        <button
                          key={board.name}
                          onClick={() => !isDisabled && handleBoardToggle(board.name)}
                          disabled={isDisabled}
                          title={isDisabled ? board.hint : board.tag}
                          className={cn(
                            "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all",
                            isDisabled
                              ? "opacity-40 cursor-not-allowed bg-slate-50 border-slate-200 text-slate-400"
                              : isSelected
                              ? "border-current text-white shadow-sm"
                              : "bg-white border-slate-200 text-slate-600 hover:border-slate-300"
                          )}
                          style={isSelected && !isDisabled
                            ? { backgroundColor: board.color, borderColor: board.color }
                            : undefined}
                        >
                          <div
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ backgroundColor: isSelected && !isDisabled ? "rgba(255,255,255,0.7)" : board.color }}
                          />
                          {board.label}
                          {board.remote_only && <span className="text-[10px] opacity-70">(remote)</span>}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })
          )}
        </CardContent>
      </Card>

      {/* Search button */}
      <Button
        onClick={handleSearch}
        disabled={!keywords.trim() || search.isPending}
        size="lg"
        className="w-full bg-blue-600 hover:bg-blue-700 text-white h-12 text-base font-semibold"
      >
        {search.isPending ? (
          <><Loader2 className="w-5 h-5 mr-2 animate-spin" />Searching & matching jobs…</>
        ) : (
          <><Zap className="w-5 h-5 mr-2" />Search All Boards</>
        )}
      </Button>

      {search.isError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {(search.error as Error)?.message || "Search failed. Make sure the backend is running."}
        </div>
      )}

      {result && !search.isPending && <SearchResults result={result} />}
    </div>
  )
}

function SearchResults({ result }: { result: SearchResponse }) {
  const { total_saved, experience_years, experience_method, jobs } = result

  const boardCounts = jobs.reduce<Record<string, number>>((acc, j) => {
    acc[j.source] = (acc[j.source] || 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-4">
      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="pt-5">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <div className="text-2xl font-bold text-blue-700">{total_saved}</div>
              <div className="text-blue-600 text-sm">jobs saved to your Dashboard</div>
              {experience_years > 0 && (
                <div className="text-slate-500 text-xs mt-1 flex items-center gap-1">
                  <Info className="w-3 h-3" />
                  Sorted by {experience_years}-year experience match, then AI score
                  {experience_method === "calculated" && " (experience calculated from work history)"}
                </div>
              )}
              <div className="text-slate-500 text-xs mt-1">
                Go to Dashboard → open a job → click "Check ATS" before applying
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(boardCounts).map(([board, count]) => (
                <span key={board} className="px-2.5 py-1 bg-white rounded-full text-xs font-medium border border-slate-200 text-slate-600">
                  {board}: {count}
                </span>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {jobs.slice(0, 5).map(job => (
        <JobCard key={job.id} job={job} compact />
      ))}

      {jobs.length > 5 && (
        <p className="text-center text-sm text-slate-500">
          +{jobs.length - 5} more jobs saved to Dashboard
        </p>
      )}

      <div className="text-center">
        <a
          href="/dashboard"
          className="inline-flex items-center gap-2 text-blue-600 hover:underline text-sm font-medium"
        >
          Go to Dashboard to review all jobs →
        </a>
      </div>
    </div>
  )
}
