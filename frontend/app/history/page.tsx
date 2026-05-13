"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getJobs, getJobStats, updateJobStatus, restoreJob } from "@/lib/api"
import type { Job, JobStatus } from "@/lib/types"
import { JobCard } from "@/components/jobs/job-card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent } from "@/components/ui/card"
import { Search, Download } from "lucide-react"
import { Button } from "@/components/ui/button"

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all",          label: "All statuses" },
  { value: "shortlisted",  label: "Saved"        },
  { value: "applied_link", label: "Applied"      },
  { value: "following_up", label: "Following Up" },
  { value: "interview",    label: "Interview"    },
  { value: "offer",        label: "Offer"        },
  { value: "skipped",      label: "Skipped"      },
]

const SOURCE_OPTIONS = [
  "All", "JSearch", "Adzuna", "The Muse", "Arbeitnow",
  "RemoteOK", "Remotive", "Jobicy", "Himalayas", "USAJobs", "Findwork", "Jooble",
]

const SORT_OPTIONS = [
  { value: "match",   label: "Match Score ↓" },
  { value: "newest",  label: "Newest First"  },
  { value: "company", label: "Company A–Z"   },
]

export default function HistoryPage() {
  const qc = useQueryClient()
  const [q, setQ]             = useState("")
  const [statusF, setStatus]  = useState("all")
  const [sourceF, setSource]  = useState("All")
  const [sortBy, setSort]     = useState("match")
  const [h1bOnly, setH1b]     = useState(false)
  const [remoteOnly, setRemote] = useState(false)

  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: getJobStats })
  const { data: allJobs = [], isLoading } = useQuery({
    queryKey: ["jobs", "all"],
    queryFn: () => getJobs(),
  })

  const restore = useMutation({
    mutationFn: restoreJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  })

  // Client-side filter + dedup
  const seen = new Set<string>()
  let jobs = allJobs.filter(j => {
    if (seen.has(j.link)) return false
    seen.add(j.link)
    return true
  })

  if (q.trim()) {
    const lq = q.toLowerCase()
    jobs = jobs.filter(j =>
      j.title.toLowerCase().includes(lq) ||
      j.company.toLowerCase().includes(lq) ||
      (j.location || "").toLowerCase().includes(lq)
    )
  }
  if (statusF !== "all") jobs = jobs.filter(j => j.status === statusF)
  if (sourceF !== "All") jobs = jobs.filter(j => j.source === sourceF)
  if (h1bOnly)           jobs = jobs.filter(j => j.h1b_mention)
  if (remoteOnly)        jobs = jobs.filter(j => j.remote)

  jobs = [...jobs].sort((a, b) =>
    sortBy === "match"   ? (b.match_score || 0) - (a.match_score || 0) :
    sortBy === "newest"  ? (b.scraped_at || "").localeCompare(a.scraped_at || "") :
    (a.company || "").localeCompare(b.company || "")
  )

  const exportCSV = () => {
    const headers = ["Title","Company","Source","Match%","ATS%","Status","Remote","H1B","Salary","Posted","Applied","Link"]
    const rows = jobs.map(j => [
      j.title, j.company, j.source,
      j.match_score.toFixed(1),
      j.ats_score != null ? j.ats_score.toFixed(1) : "",
      j.status,
      j.remote ? "Yes" : "No",
      j.h1b_mention ? "Yes" : "No",
      j.salary_text || "",
      j.date_posted || "",
      j.applied_at?.slice(0, 10) || "",
      j.link,
    ])
    const csv = [headers, ...rows].map(r => r.map(c => `"${c}"`).join(",")).join("\n")
    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url; a.download = "resumewing_jobs.csv"; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">History</h1>
          <p className="text-slate-500 text-sm mt-1">Complete log of every job tracked</p>
        </div>
        <Button variant="outline" onClick={exportCSV} size="sm" className="gap-2">
          <Download className="w-4 h-4" />
          Export CSV
        </Button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: "Total",    value: stats.total },
            { label: "Applied",  value: stats.applied_total },
            { label: "Interview",value: stats.interview + stats.offer },
            { label: "H1B",      value: stats.h1b },
            { label: "Remote",   value: stats.remote },
          ].map(({ label, value }) => (
            <Card key={label} className="text-center">
              <CardContent className="pt-3 pb-3">
                <div className="text-xl font-bold text-slate-900">{value}</div>
                <div className="text-xs text-slate-500">{label}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="md:col-span-2 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search jobs..."
            value={q}
            onChange={e => setQ(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={statusF} onValueChange={v => setStatus(v ?? "all")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map(o => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sourceF} onValueChange={v => setSource(v ?? "All")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {SOURCE_OPTIONS.map(o => (
              <SelectItem key={o} value={o}>{o}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sortBy} onValueChange={v => setSort(v ?? "match")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map(o => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-4 text-sm text-slate-600">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={h1bOnly} onChange={e => setH1b(e.target.checked)} className="rounded" />
            H1B only
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={remoteOnly} onChange={e => setRemote(e.target.checked)} className="rounded" />
            Remote only
          </label>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Showing <strong>{jobs.length}</strong> of {allJobs.length} jobs
      </p>

      {/* Job list */}
      {isLoading ? (
        <div className="space-y-3">
          {[1,2,3,4,5].map(i => (
            <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <p className="text-4xl mb-3">🔍</p>
          <p className="font-medium text-slate-600">No jobs match these filters</p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(job => (
            <JobCard
              key={job.id}
              job={job}
              onStatusChange={(id, status) => {
                if (status === "shortlisted") {
                  restore.mutate(id)
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
