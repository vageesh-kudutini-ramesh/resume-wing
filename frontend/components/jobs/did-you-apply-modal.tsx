"use client"

import { AlertDialog } from "@base-ui/react/alert-dialog"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"
import { CheckCircle2, XCircle, ExternalLink } from "lucide-react"

import { acknowledgeApplyIntent, getPendingApplyIntents } from "@/lib/api"
import type { Job } from "@/lib/types"
import { cn } from "@/lib/utils"

/**
 * Did-You-Apply modal
 *
 * Shows automatically when there are pending apply-intents — i.e. jobs the
 * user clicked "Apply" on but hasn't yet confirmed Yes/No for. Behavior:
 *
 *   1. Polls /jobs/apply-intents/pending on mount, on focus, and every 30 s.
 *   2. For each pending intent, asks "Did you apply for [Title at Company]?"
 *      - Yes  → POST acknowledge {applied:true}  → job moves to Applied stage
 *      - No   → POST acknowledge {applied:false} → job stays in Saved
 *      - Both close THIS prompt; if more intents are queued the modal cycles.
 *   3. We never auto-mark — the status only changes if the user explicitly says Yes.
 *   4. Re-prompts on the same job: a fresh Apply click bumps apply_intent_at,
 *      so the backend returns it again on the next pending fetch.
 */
export function DidYouApplyModal() {
  const qc = useQueryClient()

  const { data: pending = [], refetch } = useQuery({
    queryKey: ["apply-intents", "pending"],
    queryFn:  getPendingApplyIntents,
    refetchOnWindowFocus: true,
    refetchInterval:      30_000,
    staleTime:            10_000,
  })

  // Refetch whenever the tab regains focus — catches the case where the user
  // submitted on the job site and tabbed back into the dashboard.
  useEffect(() => {
    const onFocus = () => refetch()
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [refetch])

  const ack = useMutation({
    mutationFn: ({ id, applied }: { id: number; applied: boolean }) =>
      acknowledgeApplyIntent(id, applied),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apply-intents", "pending"] })
      qc.invalidateQueries({ queryKey: ["jobs"] })
      qc.invalidateQueries({ queryKey: ["stats"] })
    },
  })

  // Show the most recent pending intent first. The backend already orders DESC.
  const current: Job | undefined = pending[0]
  const open = !!current

  return (
    <AlertDialog.Root open={open}>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop
          className={cn(
            "fixed inset-0 bg-slate-900/40 backdrop-blur-sm",
            "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
            "transition-opacity duration-150",
          )}
        />
        <AlertDialog.Popup
          className={cn(
            "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
            "w-[440px] max-w-[calc(100vw-2rem)] bg-white rounded-2xl shadow-2xl",
            "border border-slate-200 p-6",
            "data-[starting-style]:opacity-0 data-[starting-style]:scale-95",
            "data-[ending-style]:opacity-0 data-[ending-style]:scale-95",
            "transition-[opacity,transform] duration-200",
          )}
        >
          {current && (
            <>
              <AlertDialog.Title className="text-lg font-bold text-slate-900">
                Did you apply for this job?
              </AlertDialog.Title>

              <div className="mt-3 space-y-1">
                <p className="text-sm font-semibold text-slate-900">{current.title}</p>
                <p className="text-sm text-slate-600">{current.company}</p>
                {current.location && (
                  <p className="text-xs text-slate-400">{current.location}</p>
                )}
              </div>

              <AlertDialog.Description className="mt-4 text-sm text-slate-500 leading-relaxed">
                You opened this job&apos;s apply page. If you submitted the application,
                tap Yes — we&apos;ll move it to your Applied stage. If you didn&apos;t
                finish, tap No and we&apos;ll keep it in Saved so you can come back to it.
              </AlertDialog.Description>

              {/* Open the apply page again if the user wants to verify before answering */}
              <a
                href={current.link}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
              >
                <ExternalLink className="w-3 h-3" />
                Reopen the apply page
              </a>

              <div className="mt-6 flex items-center gap-2 justify-end">
                <button
                  onClick={() => ack.mutate({ id: current.id, applied: false })}
                  disabled={ack.isPending}
                  className={cn(
                    "flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium",
                    "border border-slate-200 text-slate-700 hover:bg-slate-50",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                  )}
                >
                  <XCircle className="w-4 h-4 text-slate-400" />
                  No, not yet
                </button>
                <button
                  onClick={() => ack.mutate({ id: current.id, applied: true })}
                  disabled={ack.isPending}
                  className={cn(
                    "flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold",
                    "bg-emerald-600 text-white hover:bg-emerald-700",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                  )}
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Yes, I applied
                </button>
              </div>

              {pending.length > 1 && (
                <p className="mt-4 text-[11px] text-slate-400 text-center">
                  +{pending.length - 1} more pending confirmation
                  {pending.length > 2 ? "s" : ""}
                </p>
              )}
            </>
          )}
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
