"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  FileText, Search, LayoutDashboard, ScanText,
  History, Settings, Briefcase, CheckCircle2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useQuery } from "@tanstack/react-query"
import { getJobStats } from "@/lib/api"

const NAV_ITEMS = [
  { href: "/resume",    label: "Resume",      icon: FileText        },
  { href: "/search",    label: "Job Search",  icon: Search          },
  { href: "/dashboard", label: "Dashboard",   icon: LayoutDashboard },
  { href: "/ats",       label: "ATS Scanner", icon: ScanText        },
  { href: "/history",   label: "History",     icon: History         },
  { href: "/settings",  label: "Settings",    icon: Settings        },
]

export function Sidebar() {
  const pathname = usePathname()
  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: getJobStats,
    staleTime: 60_000,        // treat as fresh for 1 minute
    refetchInterval: 60_000,  // background refresh every 1 minute
  })

  return (
    <aside className="w-60 bg-slate-900 flex flex-col h-full border-r border-slate-800 shrink-0">
      {/* Logo */}
      <div className="px-5 py-6 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <Briefcase className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-white font-bold text-sm leading-tight tracking-wide">
              ResumeWing
            </div>
            <div className="text-slate-500 text-[10px] uppercase tracking-widest leading-tight">
              Job Automation
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/")
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                active
                  ? "bg-blue-600 text-white shadow-sm shadow-blue-900/40"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Stats footer */}
      {stats && (
        <div className="px-5 py-4 border-t border-slate-800">
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Saved",     value: stats.shortlisted },
              { label: "Applied",   value: stats.applied_total },
              { label: "Interview", value: stats.interview + stats.offer },
              { label: "H1B",       value: stats.h1b },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <div className="text-white font-bold text-lg leading-tight">{value}</div>
                <div className="text-slate-500 text-[10px] uppercase tracking-wide">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Backend status */}
      <div className="px-5 py-3 border-t border-slate-800">
        <BackendStatus />
      </div>
    </aside>
  )
}

function BackendStatus() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const r = await fetch("http://localhost:8000/health")
      return r.json()
    },
    staleTime: 15_000,
    refetchInterval: 15_000,
    retry: false,
  })

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 text-red-400 text-xs">
        <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
        Backend offline
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 text-emerald-400 text-xs">
      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      API connected
    </div>
  )
}
