"use client"

import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getProfile, updateProfile, getBoards, clearAllData } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { CheckCircle2, ExternalLink, Settings2, User, Key, Trash2, AlertTriangle } from "lucide-react"

const API_KEY_LINKS: Record<string, { label: string; url: string; description: string; envKey: string }> = {
  JSearch:  { label: "JSearch (RapidAPI)", envKey: "JSEARCH_API_KEY",    url: "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch",  description: "Google Jobs real-time via RapidAPI · 200 req/month free" },
  Adzuna:   { label: "Adzuna",             envKey: "ADZUNA_APP_ID + ADZUNA_API_KEY", url: "https://developer.adzuna.com/",           description: "250 requests/day free · Best for US market" },
  USAJobs:  { label: "USAJobs",            envKey: "USAJOBS_API_KEY",    url: "https://developer.usajobs.gov/",                   description: "US federal government jobs · Free registration" },
  Findwork: { label: "Findwork",           envKey: "FINDWORK_API_KEY",   url: "https://findwork.dev/api/",                         description: "Tech/developer focused roles · Free key" },
  Jooble:   { label: "Jooble",             envKey: "JOOBLE_API_KEY",     url: "https://jooble.org/api/about",                     description: "High-volume job aggregator · Free key" },
}

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data: profile = {} } = useQuery({ queryKey: ["profile"], queryFn: getProfile })
  const { data: boards = [] } = useQuery({ queryKey: ["boards"], queryFn: getBoards })

  const [name, setName]           = useState("")
  const [email, setEmail]         = useState("")
  const [saved, setSaved]         = useState(false)
  const [clearConfirm, setConfirm] = useState<null | "jobs" | "all">(null)
  const [clearResult, setClearResult] = useState<string | null>(null)

  useEffect(() => {
    if (profile.candidate_name)  setName(profile.candidate_name)
    if (profile.candidate_email) setEmail(profile.candidate_email)
  }, [profile])

  const update = useMutation({
    mutationFn: updateProfile,
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const clearMut = useMutation({
    mutationFn: clearAllData,
    onSuccess: (data) => {
      setClearResult(`Cleared ${data.jobs_deleted} job${data.jobs_deleted !== 1 ? "s" : ""}${data.resumes_deleted ? ` and ${data.resumes_deleted} resume` : ""}.`)
      setConfirm(null)
      qc.invalidateQueries({ queryKey: ["stats"] })
      qc.invalidateQueries({ queryKey: ["jobs"] })
      qc.invalidateQueries({ queryKey: ["resume"] })
      setTimeout(() => setClearResult(null), 5000)
    },
  })

  const handleSaveProfile = () => {
    update.mutate({ candidate_name: name, candidate_email: email })
  }

  const handleClear = (mode: "jobs" | "all") => {
    clearMut.mutate({ include_resume: mode === "all" })
  }

  const unconfigured = boards.filter(b => !b.configured && b.tier <= 2)
  const configured   = boards.filter(b => b.configured)

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-slate-500 text-sm mt-1">Configure your profile and API keys</p>
      </div>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <User className="w-4 h-4 text-blue-600" />
            Profile
          </CardTitle>
          <CardDescription>Used to autofill job application forms via the browser extension</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-sm mb-1.5 block">Full name</Label>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="Jane Smith" />
            </div>
            <div>
              <Label className="text-sm mb-1.5 block">Email</Label>
              <Input value={email} onChange={e => setEmail(e.target.value)} placeholder="jane@example.com" />
            </div>
          </div>
          <Button onClick={handleSaveProfile} disabled={update.isPending} className="gap-2">
            {saved ? <><CheckCircle2 className="w-4 h-4" />Saved!</> : "Save Profile"}
          </Button>
        </CardContent>
      </Card>

      {/* Data reset */}
      <Card className="border-red-100">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-red-700">
            <Trash2 className="w-4 h-4" />
            Reset Data
          </CardTitle>
          <CardDescription>
            Clear stored jobs to start fresh. Your resume is kept by default so you don't need to re-upload.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {clearResult && (
            <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {clearResult}
            </div>
          )}

          {/* Confirmation prompt */}
          {clearConfirm && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl space-y-3">
              <div className="flex items-start gap-2 text-sm text-red-700">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>
                  {clearConfirm === "jobs"
                    ? "This will permanently delete all saved jobs, applied jobs, and pipeline data. Your resume will be kept."
                    : "This will delete EVERYTHING — all jobs AND your uploaded resume. You will need to re-upload your resume before searching."}
                  {" "}This cannot be undone.
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={clearMut.isPending}
                  onClick={() => handleClear(clearConfirm)}
                  className="bg-red-600 hover:bg-red-700"
                >
                  {clearMut.isPending ? "Clearing…" : "Yes, delete permanently"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setConfirm(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {!clearConfirm && (
            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                variant="outline"
                className="border-red-200 text-red-700 hover:bg-red-50 gap-2"
                onClick={() => setConfirm("jobs")}
              >
                <Trash2 className="w-4 h-4" />
                Clear all jobs (keep resume)
              </Button>
              <Button
                variant="outline"
                className="border-red-300 text-red-800 hover:bg-red-50 gap-2"
                onClick={() => setConfirm("all")}
              >
                <Trash2 className="w-4 h-4" />
                Clear everything (jobs + resume)
              </Button>
            </div>
          )}

          <p className="text-xs text-slate-400 mt-1">
            After clearing, upload your resume on the Resume page and run a fresh job search.
          </p>
        </CardContent>
      </Card>

      {/* Board status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-blue-600" />
            Job Board Status
          </CardTitle>
          <CardDescription>
            {configured.length} of {boards.length} boards configured
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {boards.map(b => (
              <div key={b.name} className="flex items-center gap-2 text-sm">
                <div className={`w-2 h-2 rounded-full shrink-0 ${b.configured ? "bg-emerald-500" : "bg-slate-300"}`} />
                <span className={b.configured ? "text-slate-700" : "text-slate-400"}>{b.label}</span>
                <span className="text-slate-300 text-xs">{b.tag}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* API Keys guide */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Key className="w-4 h-4 text-blue-600" />
            Add More API Keys
          </CardTitle>
          <CardDescription>
            Add keys to your <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">job-app-automation/.env</code> file for more job sources
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {Object.entries(API_KEY_LINKS).map(([board, info]) => {
            const boardData = boards.find(b => b.name === board)
            const isConfigured = boardData?.configured ?? false
            return (
              <div key={board} className="flex items-start gap-3 p-3 rounded-lg border border-slate-100 hover:border-slate-200 transition-colors">
                <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${isConfigured ? "bg-emerald-500" : "bg-slate-300"}`} />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-slate-700">{info.label}</span>
                    {isConfigured && (
                      <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">Active</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">{info.description}</p>
                  <code className="text-xs text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded mt-1 inline-block">
                    {info.envKey}=your_key_here
                  </code>
                </div>
                <a
                  href={info.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-blue-600 hover:underline shrink-0"
                >
                  Get key <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )
          })}

          <div className="mt-4 p-3 bg-slate-50 rounded-lg text-xs text-slate-500">
            <p className="font-medium text-slate-600 mb-1">How to add a key:</p>
            <p>1. Open <code className="bg-white px-1 py-0.5 rounded border">job-app-automation/.env</code></p>
            <p>2. Add <code className="bg-white px-1 py-0.5 rounded border">KEY_NAME=your_key_value</code></p>
            <p>3. Restart the backend server (<code className="bg-white px-1 py-0.5 rounded border">uvicorn main:app --reload</code>)</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
