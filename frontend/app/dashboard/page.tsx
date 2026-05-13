"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getJobs, getJobStats, updateJobStatus, restoreJob, getResume, deleteJob } from "@/lib/api"
import type { Job } from "@/lib/types"
import { JobCard } from "@/components/jobs/job-card"
import { DidYouApplyModal } from "@/components/jobs/did-you-apply-modal"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import { Search, Briefcase, CheckCircle, MessageCircle, Trophy, SkipForward } from "lucide-react"

const STAGE_CONFIG = [
  { id: "saved",        label: "Saved",         icon: Briefcase,     status: "shortlisted",  color: "text-blue-600"   },
  { id: "applied",      label: "Applied",        icon: CheckCircle,   status: "applied_link", color: "text-emerald-600"},
  { id: "following_up", label: "Following Up",   icon: MessageCircle, status: "following_up", color: "text-amber-600"  },
  { id: "interview",    label: "Interview",      icon: Trophy,        status: "interview",    color: "text-purple-600" },
  { id: "skipped",      label: "Skipped",        icon: SkipForward,   status: "skipped",      color: "text-slate-400"  },
]

export default function DashboardPage() {
  const qc = useQueryClient()
  const [searchQ, setSearchQ] = useState("")

  const { data: stats }  = useQuery({ queryKey: ["stats"],  queryFn: getJobStats, staleTime: 60_000 })
  const { data: resume } = useQuery({ queryKey: ["resume"], queryFn: getResume,   staleTime: 5 * 60_000 })

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => updateJobStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stats"] })
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const removejob = useMutation({
    mutationFn: (id: number) => deleteJob(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stats"] })
      qc.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  return (
    <div className="space-y-6">
      {/* Did-you-apply modal — auto-fires when there are pending intents */}
      <DidYouApplyModal />

      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Your full job application pipeline</p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {[
            { label: "Total",      value: stats.total },
            { label: "Saved",      value: stats.shortlisted },
            { label: "Applied",    value: stats.applied_total },
            { label: "Following",  value: stats.following_up },
            { label: "Interview",  value: stats.interview + stats.offer },
            { label: "H1B Jobs",   value: stats.h1b },
          ].map(({ label, value }) => (
            <Card key={label} className="text-center">
              <CardContent className="pt-4 pb-3">
                <div className="text-2xl font-bold text-slate-900">{value}</div>
                <div className="text-xs text-slate-500 font-medium mt-0.5">{label}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input
          placeholder="Search jobs across all stages..."
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Pipeline tabs */}
      <Tabs defaultValue="saved">
        <TabsList className="grid grid-cols-5 w-full">
          {STAGE_CONFIG.map(({ id, label, icon: Icon, color }) => (
            <TabsTrigger key={id} value={id} className="flex items-center gap-1.5 text-xs">
              <Icon className={`w-3.5 h-3.5 ${color}`} />
              {label}
              {stats && id === "saved" && (
                <span className="ml-1 bg-blue-600 text-white text-[10px] rounded-full px-1.5 py-0.5 font-bold">
                  {stats.shortlisted}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        {STAGE_CONFIG.map(({ id, status }) => (
          <TabsContent key={id} value={id} className="mt-4">
            <StageContent
              stage={id}
              statusFilter={status}
              searchQ={searchQ}
              resumeText={resume?.text}
              onStatusChange={(jobId, newStatus) =>
                updateStatus.mutate({ id: jobId, status: newStatus })
              }
              onDelete={(jobId) => removejob.mutate(jobId)}
            />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

function StageContent({
  stage, statusFilter, searchQ, resumeText, onStatusChange, onDelete,
}: {
  stage: string
  statusFilter: string
  searchQ: string
  resumeText?: string
  onStatusChange: (id: number, status: string) => void
  onDelete: (id: number) => void
}) {
  // Fetch all statuses for this stage
  const statuses: Record<string, string[]> = {
    saved:        ["shortlisted"],
    applied:      ["applied_email", "applied_link"],
    following_up: ["following_up"],
    interview:    ["interview", "offer"],
    skipped:      ["skipped"],
  }

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs", stage],
    queryFn: () => getJobs({ stage }),
    staleTime: 60_000,
  })

  const filtered = jobs.filter(j => {
    if (!searchQ) return true
    const q = searchQ.toLowerCase()
    return (
      j.title.toLowerCase().includes(q) ||
      j.company.toLowerCase().includes(q) ||
      (j.location || "").toLowerCase().includes(q)
    )
  })

  if (isLoading) {
    return (
      <div className="grid gap-3">
        {[1,2,3].map(i => (
          <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  if (filtered.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <div className="text-4xl mb-3">📭</div>
        <p className="font-medium">
          {searchQ ? "No jobs match your search" : `No jobs in ${stage} stage yet`}
        </p>
        {stage === "saved" && !searchQ && (
          <p className="text-sm mt-1">
            <a href="/search" className="text-blue-600 hover:underline">Run a job search</a> to get started
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500 font-medium">
        {filtered.length} job{filtered.length !== 1 ? "s" : ""}
        {stage === "saved" && resumeText && (
          <span className="ml-2 text-blue-600">— click "Check ATS" on any job before applying</span>
        )}
      </p>
      {filtered.map(job => (
        <JobCard
          key={job.id}
          job={job}
          resumeText={resumeText}
          onStatusChange={onStatusChange}
          onDelete={onDelete}
        />
      ))}
    </div>
  )
}
