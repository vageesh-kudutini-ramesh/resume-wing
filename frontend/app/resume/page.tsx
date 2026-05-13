"use client"

import { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { uploadResume, getResume } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { FileText, Upload, CheckCircle2, User, Mail, Phone, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export default function ResumePage() {
  const qc = useQueryClient()
  const [dragOver, setDragOver] = useState(false)
  const [uploadInfo, setUploadInfo] = useState<{
    filename: string; skills: string[]; name?: string; email?: string; phone?: string
  } | null>(null)

  const { data: existing } = useQuery({ queryKey: ["resume"], queryFn: getResume })

  const upload = useMutation({
    mutationFn: uploadResume,
    onSuccess: (data) => {
      setUploadInfo(data)
      qc.invalidateQueries({ queryKey: ["resume"] })
    },
  })

  const handleFile = useCallback((file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase()
    if (ext !== "pdf" && ext !== "docx") {
      alert("Only PDF and DOCX files are supported")
      return
    }
    upload.mutate(file)
  }, [upload])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const info = uploadInfo || (existing ? {
    filename: existing.filename,
    skills: existing.skills,
    name: undefined,
    email: undefined,
    phone: undefined,
  } : null)

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Resume</h1>
        <p className="text-slate-500 text-sm mt-1">
          Upload your PDF or DOCX resume. Text and skills are extracted locally — nothing is sent to external servers.
        </p>
      </div>

      {/* Active resume banner */}
      {existing && !upload.isPending && (
        <div className="flex items-center gap-3 p-4 bg-emerald-50 border border-emerald-200 rounded-xl">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <div>
            <p className="font-medium text-emerald-800 text-sm">{existing.filename}</p>
            <p className="text-emerald-600 text-xs mt-0.5">
              {existing.skills.length} skills detected · Uploaded {existing.uploaded_at?.slice(0, 10)}
            </p>
          </div>
        </div>
      )}

      {/* Drop zone */}
      <label
        htmlFor="resume-upload"
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-4 p-10 rounded-2xl border-2 border-dashed cursor-pointer transition-all",
          dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-slate-300 hover:border-blue-400 hover:bg-slate-50",
          upload.isPending && "pointer-events-none opacity-60"
        )}
      >
        {upload.isPending ? (
          <>
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
            <p className="text-slate-600 font-medium">Parsing resume...</p>
          </>
        ) : (
          <>
            <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center">
              <Upload className="w-8 h-8 text-blue-600" />
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-700">
                {dragOver ? "Drop it here" : "Drop your resume or click to upload"}
              </p>
              <p className="text-slate-400 text-sm mt-1">PDF or DOCX · Processed locally</p>
            </div>
          </>
        )}
        <input
          id="resume-upload"
          type="file"
          accept=".pdf,.docx"
          onChange={handleChange}
          className="hidden"
        />
      </label>

      {/* Upload error */}
      {upload.isError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          {(upload.error as Error)?.message || "Upload failed. Check the backend is running."}
        </div>
      )}

      {/* Parsed info */}
      {info && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-600" />
                {info.filename}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Contact info */}
              {(info.name || info.email || info.phone) && (
                <div className="space-y-2">
                  {info.name && (
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <User className="w-3.5 h-3.5 text-slate-400" />
                      {info.name}
                    </div>
                  )}
                  {info.email && (
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <Mail className="w-3.5 h-3.5 text-slate-400" />
                      {info.email}
                    </div>
                  )}
                  {info.phone && (
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <Phone className="w-3.5 h-3.5 text-slate-400" />
                      {info.phone}
                    </div>
                  )}
                  <Separator />
                </div>
              )}

              {/* Skills */}
              <div>
                <p className="text-sm font-semibold text-slate-700 mb-2">
                  Detected skills ({info.skills.length})
                </p>
                {info.skills.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {info.skills.map(skill => (
                      <span key={skill} className="px-2.5 py-1 bg-blue-50 text-blue-700 border border-blue-200 rounded-full text-xs font-medium">
                        {skill}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-400 text-sm">No skills detected. Try using a more detailed resume.</p>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-600">
            <strong className="text-slate-700">Next steps:</strong>
            {" "}Go to <a href="/search" className="text-blue-600 hover:underline">Job Search</a> to find matching roles,
            or use <a href="/ats" className="text-blue-600 hover:underline">ATS Scanner</a> to optimize your resume for a specific job.
          </div>
        </div>
      )}
    </div>
  )
}
